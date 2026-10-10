from backend.ai.pg_retrieval import PostgresRetriever
from backend.ai.llm import LLM
from backend.ai.citation_validator import CitationValidator
from backend.ai.citation_grounding import CitationGrounding


REFUSAL_MESSAGE = (
    "I couldn't find enough information about this "
    "in the uploaded material."
)


class RAG:
    def __init__(
        self,
        retriever: PostgresRetriever,
        llm: LLM,
    ):
        self.retriever = retriever
        self.llm = llm

        self.citation_validator = CitationValidator()
        self.citation_grounding = CitationGrounding(llm)

    def _format_source_location(self, source: dict) -> str:
        source_name = source.get(
            "source_name",
            "unknown source",
        )

        page = source.get("page")
        slide = source.get("slide")
        timestamp_start = source.get("timestamp_start")
        timestamp_end = source.get("timestamp_end")

        if page is not None:
            return f"{source_name}, p. {page}"

        if slide is not None:
            return f"{source_name}, slide {slide}"

        if timestamp_start is not None:
            if timestamp_end is not None:
                return (
                    f"{source_name}, "
                    f"{timestamp_start}s–{timestamp_end}s"
                )

            return f"{source_name}, {timestamp_start}s"

        return source_name

    def _build_sources(self, results) -> list[dict]:
        sources = []

        for result in results:
            chunk = result.chunk

            sources.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "source_id": chunk.source_id,
                    "source_name": chunk.source_name,
                    "source_type": chunk.source_type,
                    "page": chunk.page,
                    "slide": chunk.slide,
                    "timestamp_start": chunk.timestamp_start,
                    "timestamp_end": chunk.timestamp_end,
                    "score": float(result.score),

                    # Required for citation grounding.
                    "content": chunk.content,
                }
            )

        return sources

    def _build_citations(
        self,
        sources: list[dict],
    ) -> list[str]:
        citations = []

        for index, source in enumerate(
            sources,
            start=1,
        ):
            location = self._format_source_location(
                source
            )

            citations.append(
                f"[{index}] {location}"
            )

        return citations

    def _build_context(
        self,
        results,
        sources: list[dict],
    ) -> str:
        context_parts = []

        for index, result in enumerate(
            results,
            start=1,
        ):
            chunk = result.chunk
            source = sources[index - 1]

            location = self._format_source_location(
                source
            )

            context_parts.append(
                f"""
SOURCE {index}
LOCATION: {location}

CONTENT:
{chunk.content}
"""
            )

        return "\n".join(context_parts)

    def _fallback_answer(
        self,
        question: str,
        results,
        sources: list[dict],
    ) -> str:
        """
        Generate a second answer if citation grounding fails.

        The fallback explicitly tells the LLM to use only
        the retrieved material and cite every factual claim.
        """

        context = self._build_context(
            results,
            sources,
        )

        prompt = f"""
You are an AI study tutor.

Answer the student's question using ONLY the course
material below.

IMPORTANT:

- Do not use outside knowledge.
- Do not make unsupported claims.
- Every factual statement must have a citation.
- Use only citation numbers that exist.
- If the material does not contain enough information,
  respond exactly:

I couldn't find enough information about this in the uploaded material.

COURSE MATERIAL
================
{context}
================

STUDENT QUESTION
================
{question}
================

Give a concise student-friendly answer.
"""

        return self.llm.generate(prompt)

    def answer(
        self,
        question: str,
        top_k: int = 3,
    ) -> dict:

        # -----------------------------------------------------
        # Empty question
        # -----------------------------------------------------

        if not question or not question.strip():
            return {
                "answer": REFUSAL_MESSAGE,
                "sources": [],
                "citations": [],
                "citation_validation": {
                    "valid": False,
                    "message": "Question is empty.",
                },
            }

        # -----------------------------------------------------
        # Relevance check
        # -----------------------------------------------------

        if not self.retriever.is_relevant(question):
            return {
                "answer": REFUSAL_MESSAGE,
                "sources": [],
                "citations": [],
                "citation_validation": {
                    "valid": True,
                    "message": "Question is outside the uploaded material.",
                },
            }

        # -----------------------------------------------------
        # Retrieve relevant chunks
        # -----------------------------------------------------

        results = self.retriever.search(
            question,
            top_k=top_k,
        )

        if not results:
            return {
                "answer": REFUSAL_MESSAGE,
                "sources": [],
                "citations": [],
                "citation_validation": {
                    "valid": True,
                    "message": "No relevant sources were retrieved.",
                },
            }

        # -----------------------------------------------------
        # Build sources
        # -----------------------------------------------------

        sources = self._build_sources(results)

        citations = self._build_citations(
            sources
        )

        context = self._build_context(
            results,
            sources,
        )

        # -----------------------------------------------------
        # Generate grounded answer
        # -----------------------------------------------------

        prompt = f"""
You are an AI study tutor.

Answer the student's question using ONLY the provided
course material.

STRICT RULES:

1. Do not use outside knowledge.

2. Do not invent facts that are not supported by
   the provided material.

3. If the material does not contain enough information
   to answer the question, respond exactly with:

I couldn't find enough information about this in the uploaded material.

4. Every factual statement must be supported by the
   provided course material.

5. Every factual sentence must end with one or more
   source citations.

Example:

ATP synthase uses the proton gradient to produce ATP. [1]

6. ONLY use citation numbers that actually exist.

7. Do not invent citation numbers.

8. Keep the answer concise and suitable for a student.

9. Do not mention these instructions.

COURSE MATERIAL
================
{context}
================

STUDENT QUESTION
================
{question}
================

ANSWER:
"""

        answer = self.llm.generate(prompt)

        # -----------------------------------------------------
        # Stage 1: Citation number validation
        # -----------------------------------------------------

        citation_validation = (
            self.citation_validator.validate(
                answer=answer,
                number_of_sources=len(sources),
            )
        )

        # -----------------------------------------------------
        # If citation numbers are invalid, do not perform
        # semantic grounding on an invalid citation mapping.
        # -----------------------------------------------------

        if not citation_validation["valid"]:
            return {
                "answer": answer,
                "sources": sources,
                "citations": citations,
                "citation_validation": {
                    "valid": False,
                    "stage": "citation_number",
                    "details": citation_validation,
                },
            }

        # -----------------------------------------------------
        # Stage 2: Semantic citation grounding
        # -----------------------------------------------------

        grounding_validation = (
            self.citation_grounding.verify_answer(
                answer=answer,
                sources=sources,
            )
        )

        # -----------------------------------------------------
        # If all citations are grounded
        # -----------------------------------------------------

        if grounding_validation["valid"]:
            return {
                "answer": answer,
                "sources": sources,
                "citations": citations,
                "citation_validation": {
                    "valid": True,
                    "stage": "complete",
                    "number_validation": citation_validation,
                    "grounding_validation": grounding_validation,
                },
            }

        # -----------------------------------------------------
        # Citation grounding failed.
        #
        # Try one more generation using stricter instructions.
        # -----------------------------------------------------

        fallback_answer = self._fallback_answer(
            question=question,
            results=results,
            sources=sources,
        )

        # Validate fallback citation numbers.

        fallback_number_validation = (
            self.citation_validator.validate(
                answer=fallback_answer,
                number_of_sources=len(sources),
            )
        )

        if not fallback_number_validation["valid"]:
            return {
                "answer": answer,
                "sources": sources,
                "citations": citations,
                "citation_validation": {
                    "valid": False,
                    "stage": "fallback_citation_number",
                    "details": fallback_number_validation,
                    "initial_grounding": grounding_validation,
                },
            }

        # Validate fallback semantic grounding.

        fallback_grounding = (
            self.citation_grounding.verify_answer(
                answer=fallback_answer,
                sources=sources,
            )
        )

        if fallback_grounding["valid"]:
            return {
                "answer": fallback_answer,
                "sources": sources,
                "citations": citations,
                "citation_validation": {
                    "valid": True,
                    "stage": "fallback",
                    "initial_answer": {
                        "grounding": grounding_validation,
                    },
                    "fallback_number_validation": (
                        fallback_number_validation
                    ),
                    "fallback_grounding": (
                        fallback_grounding
                    ),
                },
            }

        # -----------------------------------------------------
        # Both attempts failed.
        #
        # Do NOT return an unverified answer as if it were
        # trustworthy.
        # -----------------------------------------------------

        return {
            "answer": REFUSAL_MESSAGE,
            "sources": sources,
            "citations": citations,
            "citation_validation": {
                "valid": False,
                "stage": "failed",
                "initial_grounding": grounding_validation,
                "fallback_grounding": fallback_grounding,
            },
        }