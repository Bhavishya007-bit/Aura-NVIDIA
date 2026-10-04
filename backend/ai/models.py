from pydantic import BaseModel


class KnowledgeUnit(BaseModel):
    source_id: int
    source_type: str
    source_name: str
    content: str

    page: int | None = None
    slide: int | None = None
    timestamp_start: float | None = None
    timestamp_end: float | None = None


class Chunk(KnowledgeUnit):
    chunk_id: str

class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float

class MCQ(BaseModel):
    question: str
    options: list[str]
    correct_answer: str
    explanation: str

    topic: str | None = None
    difficulty: str | None = None

    source_ids: list[int] = []