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
# 1. COURSE MATERIAL
# ============================================================

text = """
ATP synthase is an important enzyme involved in oxidative phosphorylation.
It uses the proton gradient across the inner mitochondrial membrane.
The movement of protons through ATP synthase provides energy for ATP production.

The electron transport chain consists of several protein complexes located
in the inner mitochondrial membrane. These complexes transfer electrons
and use the released energy to pump protons across the membrane.

Chemiosmosis is the process in which the movement of protons down their
electrochemical gradient is coupled to ATP synthesis. The proton gradient
provides the energy required for ATP synthase to produce ATP.
"""


unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content=text,
    page=142
)


# ============================================================
# 2. CHUNK THE COURSE MATERIAL
# ============================================================

chunks = chunk_knowledge_unit(
    unit,
    chunk_size=250,
    overlap=50
)


# ============================================================
# 3. CREATE EMBEDDING MODEL + RETRIEVER
# ============================================================

embedding_model = EmbeddingModel()

retriever = Retriever(embedding_model)

retriever.add_chunks(chunks)


# ============================================================
# 4. CREATE LLM
# ============================================================

llm = LLM()


# ============================================================
# 5. CREATE LEARNER MODEL
# ============================================================

learner = LearnerState(student_id=1)


# ============================================================
# 6. CREATE QUESTION COMPONENTS
# ============================================================

question_generator = QuestionGenerator(llm)

question_validator = QuestionValidator()

grounding_checker = QuestionGrounding(llm)

duplicate_detector = QuestionDuplicateDetector(
    embedding_model=embedding_model,
    similarity_threshold=0.90
)


# ============================================================
# 7. CREATE ASSESSMENT SESSION
# ============================================================

session = AssessmentSession(
    student_id=1,
    topic="Adaptive Assessment"
)


# ============================================================
# 8. CREATE ADAPTIVE ASSESSMENT
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
# 9. INITIALIZE MULTIPLE TOPICS
# ============================================================

print("\n" + "=" * 70)
print("INITIAL LEARNER STATE")
print("=" * 70)

learner.update_mastery("ATP synthase", True)
learner.update_mastery("ATP synthase", True)

learner.update_mastery("Electron transport chain", True)

learner.update_mastery("Chemiosmosis", False)


print("\nTopic Mastery:")

for topic, state in learner.topic_states.items():
    print(f"{topic}: {state.p_known:.2f}")


# ============================================================
# 10. AUTOMATICALLY FIND THE WEAKEST TOPIC
# ============================================================

weakest_topic = learner.get_weakest_topic()

if weakest_topic is None:
    raise ValueError("No weakest topic was found.")

print("\nAutomatically selected weakest topic:")
print(weakest_topic)

print("\nWeakest topic mastery:")
print(learner.get_mastery(weakest_topic))

print("\nSelected difficulty:")
print(learner.get_difficulty(weakest_topic))


# ============================================================
# 11. RETRIEVE MATERIAL FOR THE WEAKEST TOPIC
# ============================================================

retrieved_chunks = retriever.search(
    weakest_topic,
    top_k=3
)


print("\nRetrieved chunks for weakest topic:")

for result in retrieved_chunks:
    print("\nSimilarity:", round(result.score, 4))
    print("Content:", result.chunk.content)


# ============================================================
# 12. GENERATE ADAPTIVE QUESTION
# ============================================================

print("\n" + "=" * 70)
print("GENERATING ADAPTIVE QUESTION")
print("=" * 70)


mcq = assessment.generate_question(
    retrieved_chunks=retrieved_chunks
)


# ============================================================
# 13. DISPLAY QUESTION
# ============================================================

print("\nQuestion:")
print(mcq.question)

print("\nOptions:")

for i, option in enumerate(mcq.options):
    print(f"{chr(65 + i)}. {option}")


print("\nCorrect Answer:")
print(mcq.correct_answer)

print("\nDifficulty:")
print(mcq.difficulty)

print("\nTopic:")
print(mcq.topic)

print("\nExplanation:")
print(mcq.explanation)


# ============================================================
# 14. SIMULATE STUDENT ANSWER
# ============================================================

student_answer = mcq.correct_answer


result = assessment.submit_answer(
    mcq=mcq,
    student_answer=student_answer,
    topic=weakest_topic
)


# ============================================================
# 15. DISPLAY RESULT
# ============================================================

print("\n" + "=" * 70)
print("ASSESSMENT RESULT")
print("=" * 70)

print("\nStudent Answer:")
print(result["student_answer"])

print("\nCorrect Answer:")
print(result["correct_answer"])

print("\nCorrect:")
print(result["is_correct"])

print("\nUpdated Mastery:")
print(result["mastery"])

print("\nNext Difficulty:")
print(result["next_difficulty"])


# ============================================================
# 16. FINAL LEARNER STATE
# ============================================================

print("\n" + "=" * 70)
print("FINAL LEARNER STATE")
print("=" * 70)

for topic, state in learner.topic_states.items():
    print(f"{topic}: {state.p_known:.2f}")


print("\nFinal Weakest Topic:")
print(learner.get_weakest_topic())