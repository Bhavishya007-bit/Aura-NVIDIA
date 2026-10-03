from backend.ai.models import KnowledgeUnit
from backend.ai.chunking import chunk_knowledge_unit
from backend.ai.embeddings import EmbeddingModel
from backend.ai.retrieval import Retriever
from backend.ai.llm import LLM
from backend.ai.rag import RAG


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
# 5. Create LLM
# --------------------------------------------------

llm = LLM()


# --------------------------------------------------
# 6. Create RAG system
# --------------------------------------------------

rag = RAG(
    retriever=retriever,
    llm=llm
)


# --------------------------------------------------
# 7. Test question inside the material
# --------------------------------------------------

question_1 = "How does ATP synthase produce ATP?"

result_1 = rag.answer(question_1)


print("\n")
print("=" * 70)
print("QUESTION 1")
print("=" * 70)

print(question_1)

print("\nANSWER")
print("-" * 70)

print(result_1["answer"])

print("\nSOURCES")
print("-" * 70)

for source in result_1["sources"]:

    print(f"File: {source['source_name']}")
    print(f"Page: {source['page']}")
    print(f"Similarity: {source['score']:.4f}")
    print(f"Content: {source['content']}")
    print()


# --------------------------------------------------
# 8. Test question outside the material
# --------------------------------------------------

question_2 = "What is the capital of France?"

result_2 = rag.answer(question_2)


print("\n")
print("=" * 70)
print("QUESTION 2")
print("=" * 70)

print(question_2)

print("\nANSWER")
print("-" * 70)

print(result_2["answer"])

print("\nSOURCES")
print("-" * 70)

for source in result_2["sources"]:

    print(f"File: {source['source_name']}")
    print(f"Page: {source['page']}")
    print(f"Similarity: {source['score']:.4f}")
    print(f"Content: {source['content']}")
    print()