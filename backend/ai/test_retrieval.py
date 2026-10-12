from backend.ai.models import KnowledgeUnit
from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.embeddings import EmbeddingModel
from backend.ai.retrieval import Retriever


# ============================================================
# 1. CREATE COURSE MATERIAL FOR DIFFERENT TOPICS
# ============================================================

atp_text = """
ATP synthase is an important enzyme involved in oxidative phosphorylation.
It uses the proton gradient across the inner mitochondrial membrane.
The movement of protons through ATP synthase provides energy for ATP production.
"""

etc_text = """
The electron transport chain consists of several protein complexes located
in the inner mitochondrial membrane. These complexes transfer electrons
and use the released energy to pump protons across the membrane.
"""

dna_text = """
DNA replication is the process by which a cell copies its DNA before cell
division. DNA polymerase adds nucleotides to the growing DNA strand.
"""


# ============================================================
# 2. CREATE KNOWLEDGE UNITS
# ============================================================

atp_unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content=atp_text,
    page=142,
    topic="ATP synthase"
)

etc_unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content=etc_text,
    page=143,
    topic="Electron transport chain"
)

dna_unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content=dna_text,
    page=210,
    topic="DNA replication"
)


# ============================================================
# 3. CHUNK EACH KNOWLEDGE UNIT
# ============================================================

atp_chunks = chunk_knowledge_unit(
    atp_unit,
    chunk_size=250,
    overlap=50
)

etc_chunks = chunk_knowledge_unit(
    etc_unit,
    chunk_size=250,
    overlap=50
)

dna_chunks = chunk_knowledge_unit(
    dna_unit,
    chunk_size=250,
    overlap=50
)


# ============================================================
# 4. COMBINE ALL CHUNKS
# ============================================================

all_chunks = (
    atp_chunks
    + etc_chunks
    + dna_chunks
)


# ============================================================
# 5. CREATE EMBEDDING MODEL + RETRIEVER
# ============================================================

embedding_model = EmbeddingModel()

retriever = Retriever(embedding_model)

retriever.add_chunks(all_chunks)


# ============================================================
# 6. TEST NORMAL RETRIEVAL
# ============================================================

print("\n" + "=" * 70)
print("NORMAL RETRIEVAL")
print("=" * 70)

results = retriever.search(
    query="How does ATP synthase produce ATP?",
    top_k=3
)

for i, result in enumerate(results, start=1):

    chunk = result.chunk

    print(f"\nResult {i}")
    print(f"Similarity: {result.score:.4f}")
    print(f"Topic: {chunk.topic}")
    print(f"Content: {chunk.content}")


# ============================================================
# 7. TEST TOPIC-AWARE RETRIEVAL
# ============================================================

print("\n" + "=" * 70)
print("TOPIC-AWARE RETRIEVAL")
print("=" * 70)

results = retriever.search(
    query="What happens to protons during ATP production?",
    topic="ATP synthase",
    top_k=3
)

print("\nRequested topic: ATP synthase")

for i, result in enumerate(results, start=1):

    chunk = result.chunk

    print(f"\nResult {i}")
    print(f"Similarity: {result.score:.4f}")
    print(f"Topic: {chunk.topic}")
    print(f"Content: {chunk.content}")


# ============================================================
# 8. TEST TOPIC FILTERING
# ============================================================

print("\n" + "=" * 70)
print("TESTING TOPIC FILTERING")
print("=" * 70)

results = retriever.search(
    query="What does DNA polymerase do?",
    topic="DNA replication",
    top_k=3
)

print("\nRequested topic: DNA replication")

for i, result in enumerate(results, start=1):

    chunk = result.chunk

    print(f"\nResult {i}")
    print(f"Similarity: {result.score:.4f}")
    print(f"Topic: {chunk.topic}")
    print(f"Content: {chunk.content}")


# ============================================================
# 9. TEST NON-EXISTENT TOPIC
# ============================================================

print("\n" + "=" * 70)
print("TESTING NON-EXISTENT TOPIC")
print("=" * 70)

results = retriever.search(
    query="How does photosynthesis work?",
    topic="Photosynthesis",
    top_k=3
)

print("\nRequested topic: Photosynthesis")

if not results:
    print("No chunks found for this topic.")
else:
    for result in results:
        print(result.chunk.content)