from backend.ai.models import KnowledgeUnit, Chunk, RetrievedChunk
from backend.ai.embeddings import EmbeddingModel
from backend.ai.retrieval import Retriever
from backend.ai.llm import LLM
from backend.ai.question_generator import QuestionGenerator
from backend.ai.learner_model import LearnerState


# --------------------------------------------------
# 1. Create sample course material
# --------------------------------------------------

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


# --------------------------------------------------
# 2. Chunk the material
# --------------------------------------------------

from backend.ai.chunking import chunk_knowledge_unit

chunks = chunk_knowledge_unit(
    unit,
    chunk_size=250,
    overlap=50
)


# --------------------------------------------------
# 3. Create retriever
# --------------------------------------------------

embedding_model = EmbeddingModel()

retriever = Retriever(embedding_model)

retriever.add_chunks(chunks)


# --------------------------------------------------
# 4. Retrieve material for question generation
# --------------------------------------------------

query = "How does ATP synthase produce ATP?"

retrieved_chunks = retriever.search(
    query,
    top_k=3
)


# --------------------------------------------------
# 5. Create LLM
# --------------------------------------------------

llm = LLM()


# --------------------------------------------------
# 6. Create question generator
# --------------------------------------------------

generator = QuestionGenerator(llm)


# --------------------------------------------------
# 7. Generate MCQ
# --------------------------------------------------

learner = LearnerState(student_id=1)

topic = "ATP synthase"

difficulty = learner.get_difficulty(topic)

print(f"\nLearner mastery: {learner.get_mastery(topic)}")
print(f"Selected difficulty: {difficulty}")

mcq = generator.generate_mcq(
    retrieved_chunks,
    difficulty=difficulty
)

print("\n" + "=" * 70)
print("ADAPTIVE LEARNING SIMULATION")
print("=" * 70)

print(f"\nCurrent mastery: {learner.get_mastery(topic)}")
print(f"Current difficulty: {learner.get_difficulty(topic)}")


# Simulate student answering correctly
student_answer_correct = True

new_mastery = learner.update_mastery(
    topic,
    student_answer_correct
)

print("\nStudent answered: CORRECT")
print(f"Updated mastery: {new_mastery}")
print(f"Next difficulty: {learner.get_difficulty(topic)}")

# Generate the next question using updated learner state

next_difficulty = learner.get_difficulty(topic)

print("\n" + "=" * 70)
print("GENERATING NEXT QUESTION")
print("=" * 70)

print(f"\nLearner mastery: {learner.get_mastery(topic)}")
print(f"Selected difficulty: {next_difficulty}")

next_mcq = generator.generate_mcq(
    retrieved_chunks,
    difficulty=next_difficulty
)

print("\nNext Question:")
print(next_mcq.question)

print("\nOptions:")
for i, option in enumerate(next_mcq.options):
    print(f"{chr(65 + i)}. {option}")

print("\nCorrect Answer:")
print(next_mcq.correct_answer)

print("\nDifficulty:")
print(next_mcq.difficulty)

# --------------------------------------------------
# 8. Display result
# --------------------------------------------------

print("\n" + "=" * 70)
print("GENERATED MCQ")
print("=" * 70)

print(f"\nQuestion:")
print(mcq.question)

print("\nOptions:")

for i, option in enumerate(mcq.options):
    letter = chr(65 + i)
    print(f"{letter}. {option}")

print(f"\nCorrect Answer:")
print(mcq.correct_answer)

print(f"\nExplanation:")
print(mcq.explanation)

print(f"\nTopic:")
print(mcq.topic)

print(f"\nDifficulty:")
print(mcq.difficulty)

print(f"\nSource IDs:")
print(mcq.source_ids)