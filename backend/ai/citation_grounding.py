
import json
import re

from backend.ai.llm import LLM


class CitationGrounding:
    """
    Verifies whether citations in a RAG answer are supported
    by their corresponding source content.
    """

    CITATION_PATTERN = re.compile(r"\[(\d+)\]")

    def __init__(self, llm: LLM):
        self.llm = llm

    def _extract_citations(self, text: str) -> list[int]:
        """Extract unique citation numbers such as [1], [2], [3]."""
        citations = [
            int(number)
            for number in self.CITATION_PATTERN.findall(text)
        ]
        return list(dict.fromkeys(citations))

    def _extract_claims(self, answer: str) -> list[dict]:
        """
        Extract the sentence or claim immediately preceding each
        citation. Adjacent citations can support the same claim.
        """
        claims = []

        for match in self.CITATION_PATTERN.finditer(answer):
            prefix = answer[:match.start()].strip()

            # Remove earlier adjacent citations from the claim text.
            prefix = re.sub(r"(?:\s*\[\d+\])+\s*$", "", prefix).strip()

            # Remove punctuation immediately before the citation.
            prefix = re.sub(r"[.!?]+$", "", prefix).strip()

            if not prefix:
                continue

            # Find the start of the last sentence.
            boundary = max(
                prefix.rfind("."),
                prefix.rfind("!"),
                prefix.rfind("?"),
                prefix.rfind("\n"),
            )

            claim = prefix[boundary + 1:].strip()

            if claim:
                claims.append({
                    "claim": claim,
                    "citation": int(match.group(1)),
                })

        return claims

    @staticmethod
    def _parse_json_response(response: str) -> dict | None:
        """Parse JSON even when the model wraps it in Markdown."""
        if not response or not response.strip():
            return None

        cleaned = response.strip()

        # Remove Markdown code fences if present.
        cleaned = re.sub(
            r"^\s*```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

        # Try parsing the entire response first.
        try:
            result = json.loads(cleaned)
            return result if isinstance(result, dict) else None
        except json.JSONDecodeError:
            pass

        # If extra text surrounds the JSON, parse the first JSON object.
        decoder = json.JSONDecoder()

        for index, character in enumerate(cleaned):
            if character != "{":
                continue

            try:
                result, _ = decoder.raw_decode(cleaned[index:])
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

        return None

    def verify_claim(self, claim: str, source: str) -> dict:
        """Ask the LLM whether a source supports a claim."""

        prompt = f"""
You are a citation verification system.

Determine whether the SOURCE directly supports the CLAIM.
Use only the provided source. Do not use outside knowledge.

CLAIM:
{claim}

SOURCE:
{source}

Return exactly one JSON object with these fields:
{{
    "supported": true,
    "reason": "Short explanation"
}}

Use supported=false if the source does not directly support
the claim or only partially supports it.

Return JSON only. Do not use Markdown code fences.
"""

        try:
            response = self.llm.generate(prompt)
        except Exception as error:
            return {
                "supported": False,
                "reason": f"Citation verification failed: {error}",
            }

        result = self._parse_json_response(response)

        if result is None:
            return {
                "supported": False,
                "reason": "Citation verifier returned invalid JSON.",
            }

        supported = result.get("supported")

        if not isinstance(supported, bool):
            return {
                "supported": False,
                "reason": "Citation verifier returned an invalid result.",
            }

        return {
            "supported": supported,
            "reason": str(result.get("reason", "No reason provided.")),
        }

    def verify_answer(self, answer: str, sources: list[dict]) -> dict:
        """Verify each cited claim against its corresponding source."""

        if not answer or not answer.strip():
            return {
                "valid": False,
                "answer": answer,
                "results": [],
                "message": "Answer is empty.",
            }

        if not sources:
            return {
                "valid": False,
                "answer": answer,
                "results": [],
                "message": "No sources are available.",
            }

        claims = self._extract_claims(answer)

        if not claims:
            return {
                "valid": False,
                "answer": answer,
                "results": [],
                "message": "No cited claims could be extracted.",
            }

        results = []

        for item in claims:
            claim = item["claim"]
            citation_number = item["citation"]

            if citation_number < 1 or citation_number > len(sources):
                results.append({
                    "claim": claim,
                    "citation": citation_number,
                    "supported": False,
                    "reason": "Citation number does not correspond to an available source.",
                })
                continue

            source_text = sources[citation_number - 1].get("content", "")

            if not source_text:
                results.append({
                    "claim": claim,
                    "citation": citation_number,
                    "supported": False,
                    "reason": "Source contains no content.",
                })
                continue

            verification = self.verify_claim(
                claim=claim,
                source=source_text,
            )

            results.append({
                "claim": claim,
                "citation": citation_number,
                "supported": verification["supported"],
                "reason": verification["reason"],
            })

        all_supported = bool(results) and all(
            result["supported"] for result in results
        )

        return {
            "valid": all_supported,
            "answer": answer,
            "results": results,
            "message": (
                "All cited claims are supported."
                if all_supported
                else "One or more cited claims are not supported."
            ),
        }
