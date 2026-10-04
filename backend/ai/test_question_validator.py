from backend.ai.models import MCQ
from backend.ai.question_validator import QuestionValidator


validator = QuestionValidator()


# ============================================================
# TEST 1 — VALID QUESTION
# ============================================================

valid_mcq = MCQ(
    question="According to the material, what provides energy for ATP production?",
    options=[
        "Oxidative phosphorylation",
        "The movement of protons through ATP synthase",
        "The inner mitochondrial membrane",
        "ATP synthase"
    ],
    correct_answer="The movement of protons through ATP synthase",
    explanation="The material states that the movement of protons through ATP synthase provides energy for ATP production.",
    topic="ATP synthase",
    difficulty="easy",
    source_ids=[1]
)


# ============================================================
# TEST 2 — INVALID QUESTION
# ============================================================

invalid_mcq = MCQ(
    question="What does ATP synthase use?",
    options=[
        "Proton gradient",
        "Proton gradient",
        "Electron gradient"
    ],
    correct_answer="Oxygen gradient",
    explanation="ATP synthase uses the movement of protons.",
    topic="ATP synthase",
    difficulty="easy",
    source_ids=[1]
)


# ============================================================
# VALID QUESTION TEST
# ============================================================

print("\n" + "=" * 70)
print("VALID QUESTION TEST")
print("=" * 70)

is_valid, errors = validator.validate(valid_mcq)

print("\nValid:", is_valid)

if errors:
    print("\nErrors:")
    for error in errors:
        print("-", error)


# ============================================================
# INVALID QUESTION TEST
# ============================================================

print("\n" + "=" * 70)
print("INVALID QUESTION TEST")
print("=" * 70)

is_valid, errors = validator.validate(invalid_mcq)

print("\nValid:", is_valid)

if errors:
    print("\nErrors:")
    for error in errors:
        print("-", error)

# ============================================================
# TEST 3 — MALFORMED TEXT
# ============================================================

malformed_mcq = MCQ(
    question="How does ATP synthase produce ATP?",
    options=[
        "Movementthrough ATP synthase provides energy",
        "Protons move through ATP synthase",
        "ATP synthase uses a proton gradient",
        "The electron transport chain pumps protons"
    ],
    correct_answer="Movementthrough ATP synthase provides energy",
    explanation="The movementthrough ATP synthase provides energy for ATP production.",
    topic="ATP synthase",
    difficulty="medium",
    source_ids=[1]
)


print("\n" + "=" * 70)
print("MALFORMED TEXT TEST")
print("=" * 70)

is_valid, errors = validator.validate(malformed_mcq)

print("\nValid:", is_valid)

if errors:
    print("\nErrors:")
    for error in errors:
        print("-", error)