from dataclasses import dataclass, field

from backend.ai.models import MCQ


@dataclass
class AssessmentResult:
    question: MCQ
    student_answer: str
    is_correct: bool
    mastery: float


@dataclass
class AssessmentSession:

    student_id: int
    topic: str

    results: list[AssessmentResult] = field(default_factory=list)

    def add_result(
        self,
        question: MCQ,
        student_answer: str,
        is_correct: bool,
        mastery: float
    ) -> None:

        result = AssessmentResult(
            question=question,
            student_answer=student_answer,
            is_correct=is_correct,
            mastery=mastery
        )

        self.results.append(result)

    def get_total_questions(self) -> int:

        return len(self.results)

    def get_correct_answers(self) -> int:

        return sum(
            result.is_correct
            for result in self.results
        )

    def get_incorrect_answers(self) -> int:

        return (
            self.get_total_questions()
            - self.get_correct_answers()
        )

    def get_accuracy(self) -> float:

        total = self.get_total_questions()

        if total == 0:
            return 0.0

        correct = self.get_correct_answers()

        return round((correct / total) * 100, 2)