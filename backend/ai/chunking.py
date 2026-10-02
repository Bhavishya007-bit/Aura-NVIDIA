from .models import KnowledgeUnit, Chunk
import uuid


def chunk_knowledge_unit(
    unit: KnowledgeUnit,
    chunk_size: int = 500,
    overlap: int = 50
) -> list[Chunk]:

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if overlap < 0:
        raise ValueError("overlap cannot be negative")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = unit.content.strip()

    if not text:
        return []

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk_text = text[start:end]

        chunk = Chunk(
            chunk_id=str(uuid.uuid4()),
            source_id=unit.source_id,
            source_type=unit.source_type,
            source_name=unit.source_name,
            content=chunk_text,
            page=unit.page,
            slide=unit.slide,
            timestamp_start=unit.timestamp_start,
            timestamp_end=unit.timestamp_end
        )

        chunks.append(chunk)

        if end >= len(text):
            break

        start = end - overlap

    return chunks