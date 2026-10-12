import numpy as np

from backend.ai.embeddings import EmbeddingModel
from backend.ai.models import Chunk, RetrievedChunk


RELEVANCE_THRESHOLD = 0.50
MIN_CHUNK_SCORE = 0.45


class Retriever:

    def __init__(self, embedding_model: EmbeddingModel):
        self.embedding_model = embedding_model
        self.chunks: list[Chunk] = []
        self.embeddings = None

    def add_chunks(self, chunks: list[Chunk]):

        if not chunks:
            return

        texts = [chunk.content for chunk in chunks]

        embeddings = self.embedding_model.embed_documents(texts)

        if self.embeddings is None:
            self.embeddings = embeddings
        else:
            self.embeddings = np.vstack([
                self.embeddings,
                embeddings
            ])

        self.chunks.extend(chunks)

    
    def search(
        self,
        query: str,
        top_k: int = 3,
        topic: str | None = None,
        source_id: int | None = None,
    ):
        if not self.chunks:
            return []

        query_embedding = self.embedding_model.embed_query(query)
        scores = self.embeddings @ query_embedding

        candidate_indices = []

        for index, chunk in enumerate(self.chunks):
            if topic is not None and chunk.topic != topic:
                continue

            if source_id is not None and chunk.source_id != source_id:
                continue

            # Skip chunks that contain only a short title
            if len(chunk.content.split()) < 5:
                continue

            candidate_indices.append(index)

        if not candidate_indices:
            return []

        sorted_indices = sorted(
            candidate_indices,
            key=lambda index: scores[index],
            reverse=True
        )

        top_indices = [
            index
            for index in sorted_indices
            if scores[index] >= MIN_CHUNK_SCORE
        ][:top_k]

        results = []

        for index in top_indices:
            results.append(
                RetrievedChunk(
                    chunk=self.chunks[index],
                    score=float(scores[index])
                )
            )

        return results


    def is_relevant(
        self,
        query: str,
        topic: str | None = None
    ) -> bool:

        results = self.search(
            query=query,
            top_k=1,
            topic=topic
        )

        if not results:
            return False

        best_score = results[0].score

        return best_score >= RELEVANCE_THRESHOLD