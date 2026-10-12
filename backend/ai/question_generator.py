from backend.ai.llm import LLM
from backend.ai.models import MCQ, RetrievedChunk


class QuestionGenerator:

    def __init__(self, llm: LLM):
        self.llm = llm


    def generate_mcq(
        self,
        retrieved_chunks: list[RetrievedChunk],
        difficulty: str,
        previous_questions: list[str] | None = None
    ) -> MCQ:

        if not retrieved_chunks:
            raise ValueError("No course material provided.")

        context_parts = []

        for i, result in enumerate(retrieved_chunks, start=1):
            chunk = result.chunk
            context_parts.append(
                f"Source {i}\n"
                f"Content:\n{chunk.content}"
            )

        context = "\n\n".join(context_parts)

        previous_questions = previous_questions or []

        if previous_questions:
            history_text = "\n".join(
                f"- {question}" for question in previous_questions
            )
        else:
            history_text = "No previously answered questions."

        prompt = f"""
You are an AI question generator for an educational study platform.

Generate exactly ONE multiple-choice question using ONLY the
provided course material. Do not use outside knowledge.

DIFFICULTY RULES

EASY:
- Test direct recall of an important fact.
- Keep the question and options concise.

MEDIUM:
- Require the learner to connect, compare, or interpret information.
- The answer must be supported by the material.

HARD:
- Require reasoning using multiple pieces of information.
- Test distinctions between closely related concepts.

Requested difficulty: {difficulty}

QUESTION REQUIREMENTS

- Generate exactly ONE specific, meaningful question.
- Do not invent facts or use outside knowledge.
- The correct answer and explanation must be supported by the material.
- Generate exactly four options, A, B, C, and D.
- All options must belong to the same conceptual category.
- Distractors must be plausible.
- Only ONE option can be correct.
- Avoid making the correct option obviously longer than the others.

QUESTION HISTORY — IMPORTANT

The following questions have already been answered by this student
for this topic:

{history_text}

Do not repeat any question in this history.
Do not merely reword a previous question.
Test a different fact, relationship, application, or concept whenever
the provided material supports it.
If history is empty, generate a suitable new question.

OUTPUT FORMAT

Return ONLY the following format:

QUESTION:
<question>

OPTIONS:
A. <option>
B. <option>
C. <option>
D. <option>

CORRECT:
<correct option letter: A, B, C, or D>

EXPLANATION:
<brief explanation>

TOPIC:
<topic>

DIFFICULTY:
<easy/medium/hard>

COURSE MATERIAL

{context}
"""

        response = self.llm.generate(prompt)

        return self._parse_response(
            response=response,
            retrieved_chunks=retrieved_chunks
        )

    
    def _parse_response(
        self,
        response: str,
        retrieved_chunks: list[RetrievedChunk]
    ) -> MCQ:

        import re

        # Normalize common Markdown formatting from LLM responses.
        text = response.replace("\r\n", "\n").strip()
        text = re.sub(r"```(?:text|markdown)?", "", text, flags=re.IGNORECASE)
        text = text.replace("```", "")
        text = re.sub(r"\*\*(QUESTION|OPTIONS|CORRECT|EXPLANATION|TOPIC|DIFFICULTY):\*\*", r"\1:", text, flags=re.IGNORECASE)

        labels = r"QUESTION|OPTIONS|CORRECT|EXPLANATION|TOPIC|DIFFICULTY"

        # Accept labels with or without their values on the same line.
        pattern = re.compile(
            rf"^\s*(?:\*\*)?({labels})(?:\*\*)?\s*:\s*(.*)$",
            re.IGNORECASE
        )

        sections = {
            "QUESTION": [],
            "OPTIONS": [],
            "CORRECT": [],
            "EXPLANATION": [],
            "TOPIC": [],
            "DIFFICULTY": [],
        }

        current_section = None

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            match = pattern.match(line)

            if match:
                current_section = match.group(1).upper()
                value = match.group(2).strip()

                if value:
                    sections[current_section].append(value)

                continue

            if current_section == "OPTIONS":
                option_match = re.match(
                    r"^[A-D][.)]\s*(.+)$",
                    line,
                    re.IGNORECASE
                )

                if option_match:
                    sections["OPTIONS"].append(
                        option_match.group(1).strip()
                    )

            elif current_section is not None:
                sections[current_section].append(line)

        question = " ".join(sections["QUESTION"]).strip()
        options = sections["OPTIONS"]
        correct_text = " ".join(sections["CORRECT"]).strip()
        explanation = " ".join(sections["EXPLANATION"]).strip()
        topic = " ".join(sections["TOPIC"]).strip()
        difficulty = " ".join(sections["DIFFICULTY"]).strip().lower()

        # Accept "A", "A.", "Option A", or "A. answer text".
        correct_match = re.match(
            r"^(?:OPTION\s+)?([A-D])(?:[.)\s]|$)",
            correct_text,
            re.IGNORECASE
        )

        if not correct_match:
            raise ValueError(
                "Could not parse the correct answer from the LLM response. "
                f"Received CORRECT section: {correct_text!r}. "
                f"Response preview: {response[:1000]!r}"
            )

        correct_letter = correct_match.group(1).upper()

        if len(options) != 4:
            raise ValueError(
                f"Expected 4 options, got {len(options)}. "
                f"Response preview: {response[:1000]!r}"
            )

        if not question:
            raise ValueError("Generated question is empty.")

        if not explanation:
            raise ValueError("Generated explanation is empty.")

        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError(
                f"Invalid generated difficulty: {difficulty!r}"
            )

        correct_index = ord(correct_letter) - ord("A")
        correct_answer = options[correct_index]

        source_ids = list({
            result.chunk.source_id
            for result in retrieved_chunks
        })

        return MCQ(
            question=question,
            options=options,
            correct_answer=correct_answer,
            explanation=explanation,
            topic=topic or None,
            difficulty=difficulty,
            source_ids=source_ids
        )
