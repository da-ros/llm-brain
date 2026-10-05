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
import shutil
import subprocess
import tempfile
from pathlib import Path
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

    def embed_video(self, payload: bytes) -> list[float] | None:
        """Embed sampled video frames. None when no frame can be decoded."""
        ...


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _average_vectors(vectors: list[list[float]]) -> list[float]:
    """Mean of frame vectors, then L2-normalized back onto the unit sphere."""
    width = len(vectors[0])
    total = [0.0] * width
    for vector in vectors:
        for index, value in enumerate(vector):
            total[index] += value
    count = float(len(vectors))
    return _l2_normalize([value / count for value in total])


def _timestamps(duration: float | None) -> list[float]:
    """Seconds for the start, middle, and end of the clip."""
    if duration is None or duration <= 0:
        return [0.0]
    end = max(0.0, duration - 0.05)
    return [0.0, duration / 2.0, end]


def _probe_duration(path: Path) -> float | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return None
    try:
        value = float(result.stdout.strip())
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def _extract_frame(path: Path, stamp: float) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-ss",
            f"{stamp:.3f}",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-",
        ],
        check=False,
        capture_output=True,
        timeout=20,
    )
    if result.returncode != 0 or not result.stdout:
        return b""
    return result.stdout


def _frames_with_ffmpeg(payload: bytes) -> list[bytes]:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg is not installed")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "clip.mp4"
        path.write_bytes(payload)
        frames: list[bytes] = []
        seen: set[bytes] = set()
        for stamp in _timestamps(_probe_duration(path)):
            frame = _extract_frame(path, stamp)
            if frame and frame not in seen:
                seen.add(frame)
                frames.append(frame)
        return frames


def sample_video_frames(payload: bytes) -> list[bytes]:
    """JPEG bytes for the start, middle, and end frames. Empty when undecodable."""
    if not payload:
        return []
    try:
        return _frames_with_ffmpeg(payload)
    except Exception:
        logger.warning("Could not decode video frames")
        return []


def embed_sampled_frames(embed_image, payload: bytes) -> list[float] | None:
    """Embed each decoded frame as an image and average the vectors."""
    vectors: list[list[float]] = []
    for frame in sample_video_frames(payload):
        try:
            vectors.append(embed_image(frame))
        except Exception:
            logger.warning("Skipping a video frame that is not an image")
    if not vectors:
        return None
    return _average_vectors(vectors)


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

    def embed_video(self, payload: bytes) -> list[float] | None:
        return embed_sampled_frames(self.embed_image, payload)


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

    def embed_video(self, payload: bytes) -> list[float] | None:
        """Embed the start, middle, and end frames. None when none of them decode."""
        return embed_sampled_frames(self.embed_image, payload)


def create_embedder() -> Embedder:
    """Factory: mock (default) or Qwen3-VL-Embedding-2B."""
    settings = get_settings()
    if settings.EMBEDDING_MOCK:
        return MockEmbedder(dim=settings.EMBEDDING_DIM)
    return QwenVLEmbedder(settings.EMBEDDING_MODEL, dim=settings.EMBEDDING_DIM)
