from backend.ai.llm import LLM
from backend.ai.models import MCQ, RetrievedChunk


class QuestionGrounding:

    def __init__(self, llm: LLM):
        self.llm = llm

    def verify(
        self,
        mcq: MCQ,
        retrieved_chunks: list[RetrievedChunk]
    ) -> tuple[bool, str]:

        if not retrieved_chunks:
            return False, "No course material provided."

        context_parts = []

        for i, result in enumerate(retrieved_chunks, start=1):
            context_parts.append(
                f"Source {i}:\n"
                f"{result.chunk.content}"
            )

        context = "\n\n".join(context_parts)

        prompt = f"""
You are a strict grounding verifier for an educational AI system.

Your job is to determine whether the generated MCQ is fully supported
by the provided course material.

Do NOT use outside knowledge.

COURSE MATERIAL:
----------------
{context}
----------------

QUESTION:
{mcq.question}

OPTIONS:
{chr(10).join(f"- {option}" for option in mcq.options)}

CORRECT ANSWER:
{mcq.correct_answer}

EXPLANATION:
{mcq.explanation}

Check all three:
1. Is the question supported by the material?
2. Is the correct answer explicitly supported by the material?
3. Is the explanation supported by the material?

Return exactly this format:

VERDICT:
SUPPORTED

REASON:
<brief explanation>

If any important part is not supported, return:

VERDICT:
NOT_SUPPORTED

REASON:
<brief explanation>
"""

        response = self.llm.generate(prompt)

        return self._parse_response(response)

    def _parse_response(
        self,
        response: str
    ) -> tuple[bool, str]:

        lines = response.split("\n")

        verdict = ""
        reason = ""

        current_section = None

        for line in lines:

            line = line.strip()

            if not line:
                continue

            if line == "VERDICT:":
                current_section = "verdict"
                continue

            if line == "REASON:":
                current_section = "reason"
                continue

            if current_section == "verdict":
                verdict = line.upper()

            elif current_section == "reason":
                reason += " " + line

        if verdict == "SUPPORTED":
            return True, reason.strip()

        if verdict == "NOT_SUPPORTED":
            return False, reason.strip()

        return False, "Unable to determine grounding."