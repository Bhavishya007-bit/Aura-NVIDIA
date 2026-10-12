import time

import torch
from sentence_transformers import SentenceTransformer


MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"


class EmbeddingModel:
    def __init__(self):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.batch_size = 16 if device == "cuda" else 4

        print(f"[Embeddings] Loading model on {device}...", flush=True)
        started = time.perf_counter()

        self.model = SentenceTransformer(
            MODEL_NAME,
            device=device,
        )

        # Suitable for the current 1,000-character source chunks.
        # Longer inputs are truncated after this many tokens.
        self.model.max_seq_length = 1024

        elapsed = time.perf_counter() - started
        print(
            f"[Embeddings] Model loaded in {elapsed:.1f} seconds.",
            flush=True,
        )

    def embed_documents(self, texts: list[str]):
        started = time.perf_counter()

        print(
            f"[Embeddings] Encoding {len(texts)} chunks...",
            flush=True,
        )

        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        elapsed = time.perf_counter() - started
        print(
            f"[Embeddings] Encoded {len(texts)} chunks "
            f"in {elapsed:.1f} seconds.",
            flush=True,
        )

        return embeddings

    def embed_query(self, query: str):
        return self.model.encode(
            query,
            prompt_name="query",
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )