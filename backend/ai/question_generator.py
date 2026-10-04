from backend.ai.llm import LLM
from backend.ai.models import MCQ, RetrievedChunk


class QuestionGenerator:

    def __init__(self, llm: LLM):
        self.llm = llm

    def generate_mcq(
        self,
        retrieved_chunks: list[RetrievedChunk],
        difficulty: str
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

        prompt = f"""
You are an AI question generator for an educational study platform.

Your task is to generate exactly ONE multiple-choice question using
ONLY the provided course material.

Do NOT use outside knowledge.

==================================================
DIFFICULTY RULES
==================================================

EASY:
- Test direct recall of an important fact.
- The answer should be directly stated in the material.
- Do not require complex reasoning.
- Keep the question and options concise.

MEDIUM:
- Require the learner to connect, compare, or interpret information
  from the provided material.
- The answer must still be completely supported by the material.
- Distractors should be plausible.

HARD:
- Require reasoning using multiple pieces of information from
  the provided material.
- Test distinctions between closely related concepts.
- Distractors should be plausible and related to the material.
- Only one option must be correct.

Requested difficulty: {difficulty}

==================================================
QUESTION REQUIREMENTS
==================================================

- Generate exactly ONE question.
- The question must be specific and meaningful.
- Do not ask vague questions.
- Do not use phrases such as:
  "What is stated in the material?"
  "According to the passage..."
- The question should test understanding of the course material.
- Do not invent facts.
- Do not use outside knowledge.
- The correct answer must be explicitly supported by the material.
- The explanation must be supported only by the material.
- Generate exactly four options.
- All four options must belong to the same conceptual category.
- Avoid obviously unrelated distractors.
- Distractors should be plausible.
- Only ONE option can be correct.
- Do not make the correct option obviously longer or more detailed
  than the distractors.
- Avoid unnecessary wording in the options.

==================================================
OUTPUT FORMAT
==================================================

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

==================================================
COURSE MATERIAL
==================================================

{context}

==================================================
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

        sections = response.split("\n")

        question = ""
        options = []
        correct_letter = ""
        explanation = ""
        topic = ""
        difficulty = ""

        current_section = None

        for line in sections:

            line = line.strip()

            if not line:
                continue

            if line == "QUESTION:":
                current_section = "question"
                continue

            if line == "OPTIONS:":
                current_section = "options"
                continue

            if line == "CORRECT:":
                current_section = "correct"
                continue

            if line == "EXPLANATION:":
                current_section = "explanation"
                continue

            if line == "TOPIC:":
                current_section = "topic"
                continue

            if line == "DIFFICULTY:":
                current_section = "difficulty"
                continue

            if current_section == "question":

                question += " " + line

            elif current_section == "options":

                if line.startswith(("A.", "B.", "C.", "D.")):
                    options.append(line[2:].strip())

            elif current_section == "correct":

                correct_letter = line.upper()

            elif current_section == "explanation":

                explanation += " " + line

            elif current_section == "topic":

                topic = line

            elif current_section == "difficulty":

                difficulty = line.lower()

        # --------------------------------------------------
        # VALIDATE CORRECT ANSWER
        # --------------------------------------------------

        if correct_letter not in ["A", "B", "C", "D"]:
            raise ValueError(
                f"Invalid correct answer: {correct_letter}"
            )

        # --------------------------------------------------
        # VALIDATE OPTIONS
        # --------------------------------------------------

        if len(options) != 4:
            raise ValueError(
                f"Expected 4 options, got {len(options)}"
            )

        # --------------------------------------------------
        # CONVERT LETTER TO ACTUAL OPTION
        # --------------------------------------------------

        correct_index = ord(correct_letter) - ord("A")

        correct_answer = options[correct_index]

        # --------------------------------------------------
        # GET SOURCE IDS
        # --------------------------------------------------

        source_ids = list({
            result.chunk.source_id
            for result in retrieved_chunks
        })

        # --------------------------------------------------
        # CREATE MCQ OBJECT
        # --------------------------------------------------

        return MCQ(
            question=question.strip(),
            options=options,
            correct_answer=correct_answer,
            explanation=explanation.strip(),
            topic=topic.strip() or None,
            difficulty=difficulty.strip() or None,
            source_ids=source_ids
        )