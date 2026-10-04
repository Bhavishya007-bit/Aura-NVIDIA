from backend.ai.models import KnowledgeUnit
from backend.ai.chunking import chunk_knowledge_unit

text = """
ATP synthase is an important enzyme involved in oxidative phosphorylation.
It uses the proton gradient across the inner mitochondrial membrane.
The movement of protons through ATP synthase provides energy for ATP production.
This process is essential for cellular respiration and energy metabolism.
"""


unit = KnowledgeUnit(
    source_id=1,
    source_type="pdf",
    source_name="Biochemistry.pdf",
    content=text,
    page=142,
    topic="ATP synthase"

)


chunks = chunk_knowledge_unit(
    unit,
    chunk_size=100,
    overlap=20
)


for i, chunk in enumerate(chunks, start=1):
    print("=" * 60)
    print(f"Chunk {i}")
    print(f"Chunk ID: {chunk.chunk_id}")
    print(f"Source: {chunk.source_name}")
    print(f"Page: {chunk.page}")
    print("Topic:", chunk.topic)
    print(f"Content: {chunk.content}")