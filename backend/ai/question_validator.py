from backend.ai.models import MCQ


class QuestionValidator:

    def validate(self, mcq: MCQ) -> tuple[bool, list[str]]:

        errors = []

        # 1. Question must not be empty
        if not mcq.question.strip():
            errors.append("Question is empty.")

        # 2. Exactly 4 options
        if len(mcq.options) != 4:
            errors.append("MCQ must contain exactly 4 options.")

        # 3. Options must not be empty
        if any(not option.strip() for option in mcq.options):
            errors.append("One or more options are empty.")

        # 4. Options should be unique
        if len(set(mcq.options)) != len(mcq.options):
            errors.append("Options must be unique.")

        # 5. Correct answer must exist
        if not mcq.correct_answer.strip():
            errors.append("Correct answer is empty.")

        # 6. Correct answer must be one of the options
        if mcq.correct_answer not in mcq.options:
            errors.append(
                "Correct answer does not match any option."
            )

        # 7. Difficulty must be valid
        if mcq.difficulty not in ["easy", "medium", "hard"]:
            errors.append(
                "Difficulty must be easy, medium, or hard."
            )

        # 8. Topic must exist
        if not mcq.topic or not mcq.topic.strip():
            errors.append("Topic is missing.")

        # 9. Source must exist
        if not mcq.source_ids:
            errors.append("No source IDs provided.")

        if errors:
            return False, errors

        return True, []