import numpy as np

from backend.ai.embeddings import EmbeddingModel
from backend.ai.models import Chunk, RetrievedChunk

RELEVANCE_THRESHOLD = 0.50

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

    def search(self, query: str, top_k: int = 3):

        if not self.chunks:
            return []

        query_embedding = self.embedding_model.embed_query(query)

        scores = self.embeddings @ query_embedding

        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []

        for index in top_indices:
            results.append(
                RetrievedChunk(
                    chunk=self.chunks[index],
                    score=float(scores[index])
                )
            )

        return results

    def is_relevant(self, query: str) -> bool:

        results = self.search(
            query,
            top_k=1
        )

        if not results:
            return False

        best_score = results[0].score

        return best_score >= RELEVANCE_THRESHOLD