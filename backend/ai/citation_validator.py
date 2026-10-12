import re


class CitationValidator:
    """Require citations and check that their numbers refer to retrieved sources."""

    CITATION_PATTERN = re.compile(r"(?:\[(\d+)\]|【(\d+)】)")

    def validate(self, answer: str, number_of_sources: int) -> dict:
        citations = list(dict.fromkeys(
            int(number) for match in self.CITATION_PATTERN.findall(answer or "")
            for number in match if number
        ))
        invalid = [number for number in citations if number < 1 or number > number_of_sources]
        valid = bool(answer and answer.strip()) and bool(citations) and not invalid
        if not answer or not answer.strip():
            message = "Answer is empty."
        elif not citations:
            message = "The answer contains no citations."
        elif invalid:
            message = "Answer contains citations that do not correspond to retrieved sources."
        else:
            message = "All citation numbers are valid."
        return {"valid": valid, "answer": answer, "citations": citations,
                "invalid_citations": invalid, "message": message}
