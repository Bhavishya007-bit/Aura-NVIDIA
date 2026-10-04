from backend.ai.models import MCQ
import re


class QuestionValidator:

    def validate(self, mcq: MCQ) -> tuple[bool, list[str]]:

        errors = []

        # ========================================================
        # 1. QUESTION CHECKS
        # ========================================================

        # Question must not be empty
        if not mcq.question.strip():
            errors.append("Question is empty.")

        # Question should have reasonable length
        if len(mcq.question.strip()) < 10:
            errors.append("Question is too short.")

        # Question should end with a question mark
        if mcq.question.strip() and not mcq.question.strip().endswith("?"):
            errors.append("Question should end with a question mark.")

        # ========================================================
        # 2. OPTION COUNT
        # ========================================================

        if len(mcq.options) != 4:
            errors.append("MCQ must contain exactly 4 options.")

        # ========================================================
        # 3. OPTION EMPTY CHECK
        # ========================================================

        if any(not option.strip() for option in mcq.options):
            errors.append("One or more options are empty.")

        # ========================================================
        # 4. OPTION UNIQUENESS
        # ========================================================

        normalized_options = [
            option.strip().lower()
            for option in mcq.options
        ]

        if len(set(normalized_options)) != len(normalized_options):
            errors.append("Options must be unique.")

        # ========================================================
        # 5. CORRECT ANSWER
        # ========================================================

        if not mcq.correct_answer.strip():
            errors.append("Correct answer is empty.")

        # Correct answer must match one of the options
        if mcq.correct_answer not in mcq.options:
            errors.append(
                "Correct answer does not match any option."
            )

        # ========================================================
        # 6. OPTION LENGTH CHECK
        # ========================================================

        for option in mcq.options:

            if len(option.strip()) < 2:
                errors.append(
                    "One or more options are too short."
                )
                break

        # ========================================================
        # 7. OBVIOUSLY BROKEN WORD CHECK
        # ========================================================

        # Detect common cases where words are accidentally joined
        # together by the LLM.

        suspicious_patterns = [
            r"[a-z][A-Z]",
            r"\b\w+through\b",
            r"\b\w+gradient\b",
            r"\b\w+ATP\b",
            r"\b\w+proton\b"
        ]

        all_text = " ".join(
            [mcq.question] +
            mcq.options +
            [mcq.explanation]
        )

        for pattern in suspicious_patterns:

            if re.search(pattern, all_text):

                errors.append(
                    "Generated text may contain incorrectly "
                    "joined words."
                )

                break

        # ========================================================
        # 8. DIFFICULTY
        # ========================================================

        if mcq.difficulty not in [
            "easy",
            "medium",
            "hard"
        ]:
            errors.append(
                "Difficulty must be easy, medium, or hard."
            )

        # ========================================================
        # 9. TOPIC
        # ========================================================

        if not mcq.topic or not mcq.topic.strip():
            errors.append("Topic is missing.")

        # ========================================================
        # 10. SOURCE
        # ========================================================

        if not mcq.source_ids:
            errors.append("No source IDs provided.")

        # ========================================================
        # FINAL RESULT
        # ========================================================

        if errors:
            return False, errors

        return True, []