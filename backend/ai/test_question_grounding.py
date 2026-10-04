from backend.ai.models import KnowledgeUnit
from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.embeddings import EmbeddingModel
from backend.ai.retrieval import Retriever
from backend.ai.llm import LLM
from backend.ai.question_generator import QuestionGenerator
from backend.ai.question_grounding import QuestionGrounding


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


# ============================================================
# KNOWLEDGE UNIT
# ============================================================

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


query = "How does ATP synthase produce ATP?"

retrieved_chunks = retriever.search(
    query,
    top_k=3
)


# ============================================================
# QUESTION GENERATION
# ============================================================

llm = LLM()

generator = QuestionGenerator(llm)

mcq = generator.generate_mcq(
    retrieved_chunks,
    difficulty="easy"
)


# ============================================================
# GROUNDING VERIFICATION
# ============================================================

grounding = QuestionGrounding(llm)

is_grounded, reason = grounding.verify(
    mcq,
    retrieved_chunks
)


# ============================================================
# OUTPUT
# ============================================================

print("\n" + "=" * 70)
print("GROUNDING VERIFICATION")
print("=" * 70)

print("\nQuestion:")
print(mcq.question)

print("\nCorrect Answer:")
print(mcq.correct_answer)

print("\nGrounded:")
print(is_grounded)

print("\nReason:")
print(reason)