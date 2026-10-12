from backend.ai.models import KnowledgeUnit
from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.embeddings import EmbeddingModel
from backend.ai.retrieval import Retriever


# --------------------------------------------------
# 1. Sample course material
# --------------------------------------------------

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


# --------------------------------------------------
# 2. Chunk the material
# --------------------------------------------------

chunks = chunk_knowledge_unit(
    unit,
    chunk_size=250,
    overlap=50
)


# --------------------------------------------------
# 3. Create embedding model
# --------------------------------------------------

embedding_model = EmbeddingModel()


# --------------------------------------------------
# 4. Create retriever
# --------------------------------------------------

retriever = Retriever(embedding_model)

retriever.add_chunks(chunks)


# --------------------------------------------------
# 5. Questions to test
# --------------------------------------------------

questions = [
    "How does ATP synthase produce ATP?",
    "What is oxidative phosphorylation?",
    "What is DNA polymerase?",
    "What is the capital of France?",
    "What is photosynthesis?"
]


# --------------------------------------------------
# 6. Test similarity scores
# --------------------------------------------------

for question in questions:

    results = retriever.search(
        question,
        top_k=1
    )

    best_result = results[0]

    print("=" * 70)
    print(f"Question: {question}")
    print(f"Best similarity score: {best_result['score']:.4f}")
    print(f"Retrieved content:")
    print(best_result["chunk"].content)
    print()