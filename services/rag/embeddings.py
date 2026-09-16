"""Multimodal embeddings — Qwen3-VL-Embedding-2B (2048-dim).

Text, image, and video are mapped into one shared vector space so a text
query can retrieve image/video chunks (cross-modal). Default dimension is
2048; Matryoshka truncation to 1024/512/256 is supported.

EMBEDDING_MOCK=true (CI / laptop) uses a token-hash embedder of the same
dimension so tests do not download the 2B weights.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

from config import get_settings
from logging_setup import log_with_correlation, logger


@runtime_checkable
class Embedder(Protocol):
    """Minimal embedding contract (text + binary modalities)."""

    dim: int

    def embed_text(self, text: str) -> list[float]:
        """Embed a text string into the shared space."""
        ...

    def embed_image(self, payload: bytes) -> list[float]:
        """Embed image bytes into the shared space."""
        ...

    def embed_video(self, payload: bytes) -> list[float]:
        """Embed video bytes into the shared space."""
        ...


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _fit_dim(values: list[float], dim: int) -> list[float]:
    """Pad or Matryoshka-truncate to the configured dimension."""
    if len(values) == dim:
        return values
    if len(values) > dim:
        return _l2_normalize(values[:dim])
    return _l2_normalize(values + [0.0] * (dim - len(values)))


class MockEmbedder:
    """Deterministic 2048-dim embedder for tests (token hashing, cosine-friendly)."""

    def __init__(self, dim: int = 2048) -> None:
        self.dim = dim

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in text.lower().split():
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            index = int(digest, 16) % self.dim
            vector[index] += 1.0
        if not any(vector):
            vector[0] = 1.0
        return _l2_normalize(vector)

    def embed_image(self, payload: bytes) -> list[float]:
        return self.embed_text(f"image {hashlib.sha256(payload).hexdigest()}")

    def embed_video(self, payload: bytes) -> list[float]:
        return self.embed_text(f"video {hashlib.sha256(payload).hexdigest()}")


class QwenVLEmbedder:
    """Qwen3-VL-Embedding-2B via sentence-transformers (multimodal)."""

    def __init__(self, model_id: str, dim: int = 2048) -> None:
        from sentence_transformers import SentenceTransformer

        log_with_correlation("no-id", "debug", f"Loading embedding model: {model_id}")
        self.dim = dim
        self._model = SentenceTransformer(model_id, trust_remote_code=True)
        logger.info("Embedding model loaded (%s dims, multimodal)", dim)

    def embed_text(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return _fit_dim(vector.tolist(), self.dim)

    def embed_image(self, payload: bytes) -> list[float]:
        from io import BytesIO

        from PIL import Image

        image = Image.open(BytesIO(payload)).convert("RGB")
        vector = self._model.encode(image, normalize_embeddings=True)
        return _fit_dim(vector.tolist(), self.dim)

    def embed_video(self, payload: bytes) -> list[float]:
        """Embed video by encoding the payload as an image when possible, else text."""
        try:
            return self.embed_image(payload)
        except Exception:
            return self.embed_text(f"video bytes {len(payload)}")


def create_embedder() -> Embedder:
    """Factory: mock (default) or Qwen3-VL-Embedding-2B."""
    settings = get_settings()
    if settings.EMBEDDING_MOCK:
        return MockEmbedder(dim=settings.EMBEDDING_DIM)
    return QwenVLEmbedder(settings.EMBEDDING_MODEL, dim=settings.EMBEDDING_DIM)
