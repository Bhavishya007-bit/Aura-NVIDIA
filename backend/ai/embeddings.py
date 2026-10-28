"""Qwen embeddings with explicit CPU/CUDA selection and compatible source tags."""

import os
import time
from collections import OrderedDict
from functools import lru_cache
from threading import RLock
from typing import Any
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from backend.preparation_progress import encoded as report_encoded

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

FAST_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LEGACY_MODEL = "Qwen/Qwen3-Embedding-0.6B"
MODEL_NAME = LEGACY_MODEL
STORAGE_DIMENSIONS = 1024
_load_lock = RLock()


def configured_model() -> str:
    name = os.getenv("AURA_EMBEDDING_MODEL", LEGACY_MODEL).strip()
    if name != LEGACY_MODEL:
        raise ValueError(
            "New uploads use Qwen. Set AURA_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B "
            "or run scripts/configure_embeddings.py."
        )
    return LEGACY_MODEL


def configured_device() -> str:
    requested = os.getenv("AURA_EMBEDDING_DEVICE", "auto").strip().lower()
    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError("AURA_EMBEDDING_DEVICE must be auto, cpu, or cuda.")
    available = torch.cuda.is_available()
    if requested == "cuda" and not available:
        raise RuntimeError(
            "GPU mode was requested, but PyTorch cannot use CUDA. Check your NVIDIA GPU, "
            "driver and CUDA-enabled PyTorch installation. No CPU fallback was used."
        )
    return ("cuda" if available else "cpu") if requested == "auto" else requested


@lru_cache(maxsize=2)
def _cached_model(name: str):
    return EmbeddingModel(name)


def get_embedding_model(name: str | None = None):
    # lru_cache alone permits duplicate simultaneous first loads.
    with _load_lock:
        return _cached_model(name or configured_model())


class EmbeddingModel:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or configured_model()
        if self.model_name not in {FAST_MODEL, LEGACY_MODEL}:
            raise ValueError(
                "Unrecognized embedding model in this material's metadata."
            )
        self._lock = RLock()
        self._document_lock = RLock()
        self._cache = OrderedDict()
        device = configured_device()
        self.device = device
        default_batch = (
            (8 if self.model_name == LEGACY_MODEL else 32)
            if device == "cuda"
            else (4 if self.model_name == LEGACY_MODEL else 16)
        )
        self.batch_size = int(
            os.getenv("AURA_EMBEDDING_BATCH_SIZE", str(default_batch))
        )
        if not 1 <= self.batch_size <= 128:
            raise ValueError("AURA_EMBEDDING_BATCH_SIZE must be between 1 and 128.")
        if device == "cpu":
            threads = int(
                os.getenv(
                    "AURA_EMBEDDING_THREADS",
                    str(min(4, max(1, (os.cpu_count() or 2) // 2))),
                )
            )
            torch.set_num_threads(max(1, min(threads, os.cpu_count() or 4)))
        started = time.perf_counter()
        print(f"[Embeddings] Loading {self.model_name} on {device}...", flush=True)
        # Keep FP32 weights and inference; do not quantize or substitute a
        # smaller encoder to obtain speed. GPU arithmetic can still differ
        # slightly from CPU arithmetic.
        if device == "cuda":
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
        try:
            self.model = SentenceTransformer(
                self.model_name,
                device=device,
                model_kwargs={"torch_dtype": torch.float32},
            )
        except torch.cuda.OutOfMemoryError as error:
            raise RuntimeError(
                "The embedding model cannot fit in available GPU memory at FP32. "
                "Free GPU memory or explicitly choose CPU mode; no smaller model was substituted."
            ) from error
        # Short source chunks fit the encoder's context; original text and
        # citations remain stored unchanged. Qwen retains its earlier setting.
        self.model.max_seq_length = 512 if self.model_name == FAST_MODEL else 1024
        self.dimensions = self.model.get_sentence_embedding_dimension()
        expected = 384 if self.model_name == FAST_MODEL else 1024
        if self.dimensions != expected:
            raise ValueError(
                "Embedding model dimensions do not match the expected profile."
            )
        print(
            f"[Embeddings] Model loaded in {time.perf_counter() - started:.1f} seconds.",
            flush=True,
        )

    def _storage_vectors(self, values):
        values = np.asarray(values, dtype=np.float32)
        if values.shape[-1] != self.dimensions:
            raise ValueError("The encoder returned an unexpected vector dimension.")
        # Zero padding preserves cosine similarity within the same model.
        # Model tags prevent comparing MiniLM vectors with Qwen query vectors.
        return np.pad(
            values,
            [(0, 0)] * (values.ndim - 1) + [(0, STORAGE_DIMENSIONS - self.dimensions)],
        )

    def _encode_documents(self, texts):
        while True:
            try:
                with torch.inference_mode():
                    return self.model.encode(
                        texts,
                        batch_size=self.batch_size,
                        normalize_embeddings=True,
                        convert_to_numpy=True,
                        show_progress_bar=False,
                    )
            except torch.cuda.OutOfMemoryError as error:
                if self.device != "cuda" or self.batch_size == 1:
                    raise RuntimeError(
                        "Qwen embeddings do not fit in available GPU memory. Free GPU memory "
                        "or explicitly select CPU mode; the model and precision were not reduced."
                    ) from error
                self.batch_size = max(1, self.batch_size // 2)
                torch.cuda.empty_cache()
                print(
                    f"[Embeddings] GPU memory limit: retrying batch size {self.batch_size}.",
                    flush=True,
                )

    def embed_documents(self, texts: list[str]):
        if not texts:
            return np.empty((0, STORAGE_DIMENSIONS), dtype=np.float32)
        started = time.perf_counter()
        with self._document_lock:
            unique = list(dict.fromkeys(texts))
            missing = sorted((text for text in unique if text not in self._cache), key=len)
            encoded = {}
            if missing:
                parts = []
                offset = 0
                # Emit progress after real model batches, even on a 4GB GPU
                # configured for batch size 1. OOM retries retain FP32/Qwen.
                while offset < len(missing):
                    batch = missing[offset:offset + self.batch_size]
                    # Queries may use the same encoder between document batches.
                    # Only one model inference runs at a time; document cache
                    # writes remain serialized separately.
                    with self._lock:
                        vectors = self._storage_vectors(self._encode_documents(batch))
                    if len(vectors) != len(batch):
                        raise ValueError("Embedding count does not match input count.")
                    parts.extend(vectors)
                    offset += len(batch)
                    report_encoded(len(unique) - len(missing) + offset)
                encoded_vectors = dict(zip(missing, parts))
                encoded = encoded_vectors
            result = np.stack(
                [
                    encoded[text] if text in encoded else self._cache[text]
                    for text in texts
                ]
            )
            for text in unique:
                self._cache[text] = (
                    encoded[text] if text in encoded else self._cache[text]
                )
                self._cache.move_to_end(text)
            while len(self._cache) > 2048:
                self._cache.popitem(last=False)
        print(
            f"[Embeddings] {len(texts)} chunks; {len(missing)} newly encoded; "
            f"{time.perf_counter() - started:.1f} seconds.",
            flush=True,
        )
        return result

    def embed_query(self, query: str):
        options: dict[str, Any] = {
            "normalize_embeddings": True,
            "convert_to_numpy": True,
            "show_progress_bar": False,
        }
        if self.model_name == LEGACY_MODEL:
            options["prompt_name"] = "query"
        try:
            with self._lock, torch.inference_mode():
                vector = self.model.encode(query, **options)
        except torch.cuda.OutOfMemoryError as error:
            raise RuntimeError(
                "The query cannot fit in available GPU memory. Free GPU memory or select CPU mode."
            ) from error
        return self._storage_vectors(vector)

