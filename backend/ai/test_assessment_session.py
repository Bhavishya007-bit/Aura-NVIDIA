from backend.ai.assessment_session import AssessmentSession
from backend.ai.models import MCQ


question = MCQ(
    question="Which gradient drives ATP synthase?",
    options=[
        "Proton gradient",
        "Electron gradient",
        "Oxygen gradient",
        "Glucose gradient"
    ],
    correct_answer="Proton gradient",
    explanation="ATP synthase uses the proton gradient.",
    topic="ATP synthase",
    difficulty="easy",
    source_ids=[1]
)


session = AssessmentSession(
    student_id=1,
    topic="ATP synthase"
)


session.add_result(
    question=question,
    student_answer="Proton gradient",
    is_correct=True,
    mastery=0.62
)


session.add_result(
    question=question,
    student_answer="Electron gradient",
    is_correct=False,
    mastery=0.54
)


print("Total questions:", session.get_total_questions())
print("Correct:", session.get_correct_answers())
print("Incorrect:", session.get_incorrect_answers())
print("Accuracy:", session.get_accuracy(), "%")