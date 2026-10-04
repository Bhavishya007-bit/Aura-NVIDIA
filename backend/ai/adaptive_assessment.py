from backend.ai.assessment_session import AssessmentSession
from backend.ai.models import MCQ, RetrievedChunk
from backend.ai.learner_model import LearnerState
from backend.ai.question_generator import QuestionGenerator
from backend.ai.question_validator import QuestionValidator
from backend.ai.question_grounding import QuestionGrounding
from backend.ai.question_duplicate import QuestionDuplicateDetector

class AdaptiveAssessment:

    def __init__(
        self,
        learner: LearnerState,
        question_generator: QuestionGenerator,
        question_validator: QuestionValidator,
        grounding_checker: QuestionGrounding,
        duplicate_detector: QuestionDuplicateDetector,
        session: AssessmentSession
    ):
        self.learner = learner
        self.question_generator = question_generator
        self.question_validator = question_validator
        self.grounding_checker = grounding_checker
        self.duplicate_detector = duplicate_detector
        self.session = session

    def generate_question(
        self,
        topic: str,
        retrieved_chunks: list[RetrievedChunk],
        max_attempts: int = 5
    ) -> MCQ:

        difficulty = self.learner.get_difficulty(topic)

        print(f"Learner mastery: {self.learner.get_mastery(topic)}")
        print(f"Selected difficulty: {difficulty}")

        while True:
            mcq = self.question_generator.generate_mcq(
                retrieved_chunks,
                difficulty=difficulty
            )

            is_valid, errors = self.question_validator.validate(mcq)

            if not is_valid:
                raise ValueError(
                    f"Generated MCQ failed validation: {errors}"
                )

            is_grounded, reason = self.grounding_checker.verify(
                mcq,
                retrieved_chunks
            )

            if not is_grounded:
                raise ValueError(
                    f"Generated MCQ failed grounding verification: {reason}"
                )

            # Duplicate detection
            if self.duplicate_detector.is_duplicate(mcq):
                print(
                    "Duplicate question detected. "
                    "Generating another question..."
                )
                continue

            self.duplicate_detector.add_question(mcq)
            print("Question accepted.")
            return mcq

    def submit_answer(
        self,
        mcq: MCQ,
        student_answer: str,
        topic: str
    ) -> dict:

        student_answer = student_answer.strip()

        is_correct = student_answer == mcq.correct_answer

        if not topic:
            raise ValueError("Assessment topic is missing.")

        new_mastery = self.learner.update_mastery(
            topic=topic,
            correct=is_correct
        )

        self.session.add_result(
            question=mcq,
            student_answer=student_answer,
            is_correct=is_correct,
            mastery=new_mastery
        )

        return {
            "question": mcq.question,
            "student_answer": student_answer,
            "correct_answer": mcq.correct_answer,
            "is_correct": is_correct,
            "explanation": mcq.explanation,
            "topic": topic,
            "mastery": new_mastery,
            "next_difficulty": self.learner.get_difficulty(topic)
        }