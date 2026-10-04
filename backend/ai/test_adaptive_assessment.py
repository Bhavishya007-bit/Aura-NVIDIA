from backend.ai.models import KnowledgeUnit
from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.embeddings import EmbeddingModel
from backend.ai.retrieval import Retriever
from backend.ai.llm import LLM

from backend.ai.learner_model import LearnerState
from backend.ai.question_generator import QuestionGenerator
from backend.ai.question_validator import QuestionValidator
from backend.ai.question_grounding import QuestionGrounding
from backend.ai.question_duplicate import QuestionDuplicateDetector
from backend.ai.adaptive_assessment import AdaptiveAssessment
from backend.ai.assessment_session import AssessmentSession


# ============================================================
# COURSE MATERIAL
# ============================================================

text = """
ATP synthase is an important enzyme involved in oxidative phosphorylation.
It uses the proton gradient across the inner mitochondrial membrane.
The movement of protons through ATP synthase provides energy for ATP production.

The electron transport chain consists of several protein complexes located
in the inner mitochondrial membrane. These complexes transfer electrons
and use the released energy to pump protons across the membrane.
"""


unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content=text,
    page=142
)


# ============================================================
# CHUNKING
# ============================================================

chunks = chunk_knowledge_unit(
    unit,
    chunk_size=250,
    overlap=50
)


# ============================================================
# EMBEDDINGS + RETRIEVAL
# ============================================================

embedding_model = EmbeddingModel()

retriever = Retriever(embedding_model)

retriever.add_chunks(chunks)

retrieved_chunks = retriever.search(
    "How does ATP synthase produce ATP?",
    top_k=3
)


# ============================================================
# AI COMPONENTS
# ============================================================

llm = LLM()

learner = LearnerState(
    student_id=1
)

question_generator = QuestionGenerator(llm)

question_validator = QuestionValidator()

grounding_checker = QuestionGrounding(llm)

duplicate_detector = QuestionDuplicateDetector(
    embedding_model=embedding_model,
    similarity_threshold=0.90
)


# ============================================================
# ASSESSMENT SESSION
# ============================================================

session = AssessmentSession(
    student_id=1,
    topic="ATP synthase"
)


# ============================================================
# ADAPTIVE ASSESSMENT
# ============================================================

assessment = AdaptiveAssessment(
    learner=learner,
    question_generator=question_generator,
    question_validator=question_validator,
    grounding_checker=grounding_checker,
    duplicate_detector=duplicate_detector,
    session=session
)


# ============================================================
# ASSESSMENT CONFIGURATION
# ============================================================

topic = "ATP synthase"

# Simulated student performance
#
# True  = student answers correctly
# False = student answers incorrectly

student_performance = [
    True,
    True,
    False,
    True,
    False
]


# ============================================================
# ADAPTIVE ASSESSMENT LOOP
# ============================================================

for question_number, should_be_correct in enumerate(
    student_performance,
    start=1
):

    print("\n" + "=" * 70)
    print(f"QUESTION {question_number}")
    print("=" * 70)

    # --------------------------------------------------------
    # Generate question
    # --------------------------------------------------------

    mcq = assessment.generate_question(
        topic=topic,
        retrieved_chunks=retrieved_chunks
    )

    print("\nQuestion:")
    print(mcq.question)

    print("\nOptions:")

    for i, option in enumerate(mcq.options):
        print(f"{chr(65 + i)}. {option}")

    print("\nDifficulty:")
    print(mcq.difficulty)

    # --------------------------------------------------------
    # Simulate student's answer
    # --------------------------------------------------------

    if should_be_correct:

        # Student chooses the correct answer
        student_answer = mcq.correct_answer

    else:

        # Student chooses the first incorrect answer
        student_answer = next(
            option
            for option in mcq.options
            if option != mcq.correct_answer
        )

    # --------------------------------------------------------
    # Submit answer
    # --------------------------------------------------------

    result = assessment.submit_answer(
        mcq=mcq,
        student_answer=student_answer,
        topic=topic
    )

    # --------------------------------------------------------
    # Display answer result
    # --------------------------------------------------------

    print("\nStudent Answer:")
    print(result["student_answer"])

    print("\nCorrect Answer:")
    print(result["correct_answer"])

    print("\nCorrect:")
    print(result["is_correct"])

    print("\nExplanation:")
    print(result["explanation"])

    print("\nUpdated Mastery:")
    print(result["mastery"])

    print("\nNext Difficulty:")
    print(result["next_difficulty"])


# ============================================================
# FINAL ASSESSMENT REPORT
# ============================================================

print("\n" + "=" * 70)
print("FINAL ASSESSMENT REPORT")
print("=" * 70)

print("\nStudent ID:")
print(session.student_id)

print("\nTopic:")
print(session.topic)

print("\nTotal Questions:")
print(session.get_total_questions())

print("\nCorrect:")
print(session.get_correct_answers())

print("\nIncorrect:")
print(session.get_incorrect_answers())

print("\nAccuracy:")
print(session.get_accuracy(), "%")

print("\nFinal Mastery:")
print(learner.get_mastery(topic))

print("\nFinal Difficulty:")
print(learner.get_difficulty(topic))