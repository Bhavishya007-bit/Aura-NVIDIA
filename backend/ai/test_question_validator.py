from backend.ai.models import MCQ
from backend.ai.question_validator import QuestionValidator


mcq = MCQ(
    question="According to the material, what provides energy for ATP production?",
    options=[
        "Oxidative phosphorylation",
        "The movement of protons through ATP synthase",
        "The inner mitochondrial membrane",
        "ATP synthase"
    ],
    correct_answer="The movement of protons through ATP synthase",
    explanation="The material states that the movement of protons through ATP synthase provides energy for ATP production.",
    topic="ATP synthase and proton movement",
    difficulty="easy",
    source_ids=[1]
)


validator = QuestionValidator()

is_valid, errors = validator.validate(mcq)

print("Valid:", is_valid)

if errors:
    print("\nErrors:")
    for error in errors:
        print("-", error)