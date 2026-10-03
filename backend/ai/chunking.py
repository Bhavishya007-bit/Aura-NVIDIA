from .models import KnowledgeUnit, Chunk
import uuid
import re


def split_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences while keeping each sentence intact.
    """

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    return [sentence.strip() for sentence in sentences if sentence.strip()]


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

    sentences = split_into_sentences(text)

    chunks = []
    current_sentences = []
    current_length = 0

    for sentence in sentences:

        sentence_length = len(sentence)

        # If adding this sentence exceeds the chunk size,
        # save the current chunk first.
        if (
            current_sentences
            and current_length + sentence_length + 1 > chunk_size
        ):

            chunk_text = " ".join(current_sentences)

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

            # Create overlap using the last sentence(s).
            overlap_sentences = []
            overlap_length = 0

            for previous_sentence in reversed(current_sentences):

                if overlap_length + len(previous_sentence) + 1 > overlap:
                    break

                overlap_sentences.insert(0, previous_sentence)
                overlap_length += len(previous_sentence) + 1

            current_sentences = overlap_sentences
            current_length = overlap_length

        current_sentences.append(sentence)
        current_length += sentence_length + 1

    # Add the final chunk.
    if current_sentences:

        chunk_text = " ".join(current_sentences)

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

    return chunks