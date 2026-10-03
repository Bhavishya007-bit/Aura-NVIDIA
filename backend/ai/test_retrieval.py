from backend.ai.models import KnowledgeUnit
from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.embeddings import EmbeddingModel
from backend.ai.retrieval import Retriever


text = """
ATP synthase is an important enzyme involved in oxidative phosphorylation.
It uses the proton gradient across the inner mitochondrial membrane.
The movement of protons through ATP synthase provides energy for ATP production.

The electron transport chain consists of several protein complexes located
in the inner mitochondrial membrane. These complexes transfer electrons
and use the released energy to pump protons across the membrane.

DNA replication is the process by which a cell copies its DNA before cell
division. DNA polymerase adds nucleotides to the growing DNA strand.
"""


unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content=text,
    page=142
)


chunks = chunk_knowledge_unit(
    unit,
    chunk_size=250,
    overlap=50
)


embedding_model = EmbeddingModel()

retriever = Retriever(embedding_model)

retriever.add_chunks(chunks)


query = "How does ATP synthase produce ATP?"

results = retriever.search(
    query,
    top_k=3
)


print("\nSEARCH RESULTS")
print("=" * 60)

for i, result in enumerate(results, start=1):

    chunk = result.chunk
    score = result.score

    print(f"\nResult {i}")
    print(f"Similarity: {score:.4f}")
    print(f"Source: {chunk.source_name}")
    print(f"Page: {chunk.page}")
    print(f"Content: {chunk.content}")