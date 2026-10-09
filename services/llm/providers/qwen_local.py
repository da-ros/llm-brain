"""Local Qwen3.5-4B provider — bfloat16 checkpoint on Metal or CUDA.

QWEN_MOCK=true skips the weights. CI and unit tests stay on that path.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from exceptions import InferenceTimeoutError, ModelNotFoundError, ModelUnavailableError
from providers.base import LLMResult

_TOKEN_RE = re.compile(r"\S+")


def _count_tokens(*parts: str) -> int:
    total = 0
    for part in parts:
        total += len(_TOKEN_RE.findall(part or ""))
    return max(1, total)


def _torch_device() -> str:
    """Metal on this Mac, CUDA when a GPU is present. CPU cannot run this checkpoint."""
    import torch
    from config import get_settings

    choice = (get_settings().QWEN_DEVICE or "auto").strip().lower()
    if choice == "auto":
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
        return "cpu"
    return choice


_mps_convolution_ready = False


def _install_mps_convolution_fallback() -> None:
    """Metal has no convolution_overrideable. Run that op on CPU and copy back.

    Qwen3.5's vision patch embed and its linear-attention conv call this op.
    A normal conv2d/conv3d on Metal still uses the built-in kernel.
    """
    global _mps_convolution_ready
    if _mps_convolution_ready:
        return
    import torch

    def _conv(samples, weight, bias, stride, padding, dilation, transposed, output_padding, groups):
        spatial = weight.ndim - 2
        cpu_input = samples.detach().to(device="cpu", dtype=torch.float32)
        cpu_weight = weight.detach().to(device="cpu", dtype=torch.float32)
        cpu_bias = None if bias is None else bias.detach().to(device="cpu", dtype=torch.float32)
        kwargs = {
            "stride": tuple(stride),
            "padding": tuple(padding),
            "dilation": tuple(dilation),
            "groups": int(groups),
        }
        if transposed:
            table = {
                1: torch.nn.functional.conv_transpose1d,
                2: torch.nn.functional.conv_transpose2d,
                3: torch.nn.functional.conv_transpose3d,
            }
            kwargs["output_padding"] = tuple(output_padding)
        else:
            table = {
                1: torch.nn.functional.conv1d,
                2: torch.nn.functional.conv2d,
                3: torch.nn.functional.conv3d,
            }
        out = table[spatial](cpu_input, cpu_weight, cpu_bias, **kwargs)
        return out.to(device=samples.device, dtype=samples.dtype)

    with contextlib.suppress(RuntimeError):
        # This process may already have registered the fallback.
        torch.library.impl("aten::convolution_overrideable", "MPS", _conv)
    _mps_convolution_ready = True


def flatten_content(content: Any) -> str:
    """Flatten string or multimodal content parts into text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    chunks: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            chunks.append(str(part))
            continue
        part_type = str(part.get("type", "text")).lower()
        if part_type == "text":
            chunks.append(str(part.get("text") or part.get("content") or ""))
        elif part_type in {"image", "image_url"}:
            ref = _media_ref(part, "image")
            chunks.append("[image]" if ref.startswith("data:") else f"[image:{ref}]")
        elif part_type in {"video", "video_url"}:
            ref = _media_ref(part, "video")
            chunks.append("[video]" if ref.startswith("data:") else f"[video:{ref}]")
        else:
            chunks.append(str(part.get("text") or part))
    return " ".join(chunk for chunk in chunks if chunk)


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".mpeg", ".mpg"}


def _media_parts(media: list[tuple] | None) -> list[tuple[str, bytes, str]]:
    parts: list[tuple[str, bytes, str]] = []
    for item in media or []:
        filename = item[2] if len(item) > 2 else ""
        parts.append((item[0], item[1], filename))
    return parts


def _suffix_for(kind: str, filename: str) -> str:
    """Keep the file's own extension so the processor reads the real format."""
    suffix = Path(filename or "").suffix.lower()
    allowed = _VIDEO_SUFFIXES if kind == "video" else _IMAGE_SUFFIXES
    if suffix in allowed:
        return suffix
    return ".mp4" if kind == "video" else ".png"


def _media_ref(part: dict, kind: str) -> str:
    nested = part.get(f"{kind}_url")
    if isinstance(nested, dict):
        return str(nested.get("url") or kind)
    if isinstance(nested, str):
        return nested
    return str(part.get("url") or part.get(kind) or part.get("data") or part.get("path") or kind)


def _decode_data_url(url: str) -> tuple[bytes, str] | None:
    """Return bytes and MIME for a data URL. Other URLs stay as text refs."""
    if not url.startswith("data:"):
        return None
    header, sep, data = url.partition(",")
    if not sep or not data:
        return None
    mime = header[5:].split(";", 1)[0].strip().lower()
    try:
        payload = base64.b64decode(data, validate=False)
    except Exception:
        return None
    if not payload:
        return None
    return payload, mime


def _filename_for_media(kind: str, mime: str, payload: bytes) -> str:
    by_mime = {
        "image/png": "image.png",
        "image/jpeg": "image.jpg",
        "image/jpg": "image.jpg",
        "image/webp": "image.webp",
        "image/gif": "image.gif",
        "image/bmp": "image.bmp",
        "image/tiff": "image.tiff",
        "video/mp4": "clip.mp4",
        "video/webm": "clip.webm",
        "video/quicktime": "clip.mov",
    }
    if mime in by_mime:
        return by_mime[mime]
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image.png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image.jpg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image.gif"
    if len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image.webp"
    if b"ftyp" in payload[:32]:
        return "clip.mp4"
    return "clip.mp4" if kind == "video" else "image.png"


def _inline_media_part(part: Any) -> tuple[str, bytes, str] | None:
    """Pull a data-URL image or video out of one content part."""
    if not isinstance(part, dict):
        return None
    part_type = str(part.get("type", "")).lower()
    if part_type in {"image", "image_url"}:
        kind = "image"
    elif part_type in {"video", "video_url"}:
        kind = "video"
    else:
        return None
    decoded = _decode_data_url(_media_ref(part, kind))
    if decoded is None:
        return None
    payload, mime = decoded
    return kind, payload, _filename_for_media(kind, mime, payload)


def extract_inline_media(content: Any) -> tuple[Any, list[tuple[str, bytes, str]]]:
    """Separate data-URL media from the text the prompt should keep."""
    if not isinstance(content, list):
        return content, []
    kept: list[Any] = []
    media: list[tuple[str, bytes, str]] = []
    for part in content:
        pulled = _inline_media_part(part)
        if pulled is None:
            kept.append(part)
        else:
            media.append(pulled)
    return kept, media


_IMAGE_MAX_SIDE = 1280


def _fit_image(payload: bytes, filename: str) -> tuple[bytes, str]:
    """Shrink a large screenshot so the vision tokens stay in context."""
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(payload))
        image.load()
    except Exception:
        return payload, filename
    if max(image.size) > _IMAGE_MAX_SIDE:
        image.thumbnail((_IMAGE_MAX_SIDE, _IMAGE_MAX_SIDE))
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), "image.png"


_CONTEXT_WINDOW = 262144


def _sequence_width(input_ids) -> int:
    shape = getattr(input_ids, "shape", None)
    if shape is not None:
        return int(shape[-1])
    row = input_ids[0] if input_ids and isinstance(input_ids[0], list | tuple) else input_ids
    return len(row)


def _output_budget(processor, input_width: int, requested: int | None) -> int:
    """How many new tokens to allow. None means the rest of the context window."""
    if requested is not None:
        return requested
    window = getattr(getattr(processor, "tokenizer", None), "model_max_length", _CONTEXT_WINDOW)
    if not isinstance(window, int) or window < 1 or window > 1_000_000:
        window = _CONTEXT_WINDOW
    return max(1, window - input_width)


def build_chat_prompt(messages: list[dict], context: str | None = None) -> str:
    """Build a single prompt from chat messages and optional RAG context."""
    parts: list[str] = []
    if context:
        parts.append(f"Context:\n{context}\n")
    for message in messages:
        role = message.get("role", "user")
        text = flatten_content(message.get("content", ""))
        parts.append(f"{role}: {text}")
    return "\n".join(parts)


TRIPLE_EXTRACTION_PROMPT = """You extract knowledge triples from documents.
Return ONLY a JSON array of objects with keys subject, predicate, object, metadata.
metadata must include source notes when available.

Document:
{content}
"""


def parse_triples_json(text: str) -> list[dict]:
    """Parse a JSON array of triples from model output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", stripped, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    triples: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        predicate = item.get("predicate")
        obj = item.get("object")
        if subject and predicate and obj:
            triples.append(
                {
                    "subject": str(subject),
                    "predicate": str(predicate),
                    "object": str(obj),
                    "metadata": item.get("metadata") or {},
                }
            )
    return triples


class QwenLocalProvider:
    """Qwen3.5-4B base inference on Metal or CUDA (not fine-tuned)."""

    name = "qwen-local"

    def __init__(
        self,
        model_id: str = "qwen3.5-4b",
        hf_model_id: str = "Qwen/Qwen3.5-4B",
        adapter_path: str | None = None,
        mock: bool = True,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.model_id = model_id
        self.hf_model_id = hf_model_id
        # Cloud container stays base; adapter_path is unused here (Frame 10).
        self.adapter_path = adapter_path
        self.mock = mock
        self.timeout_seconds = timeout_seconds
        self._device = "cpu"
        self._visual_model = None
        self._processor = None

    def complete(
        self,
        prompt: str,
        media: list[tuple] | None = None,
        max_new_tokens: int | None = None,
    ) -> LLMResult:
        """Complete a prompt. media items are (kind, file bytes, filename)."""
        parts = _media_parts(media)
        if self.mock:
            text = f"[Qwen3.5-4B base] {prompt.strip()}"
            if parts:
                shown = "; ".join(
                    f"{kind} sha256={hashlib.sha256(payload).hexdigest()}"
                    for kind, payload, _filename in parts
                )
                text = f"{text}\nShown: {shown}"
            return LLMResult(text=text, tokens_used=_count_tokens(prompt, text))
        if parts:
            return self._generate_visual(prompt, parts, max_new_tokens)
        return self._generate(prompt, max_new_tokens)

    def _generate_visual(
        self,
        prompt: str,
        media: list[tuple[str, bytes, str]],
        max_new_tokens: int | None = None,
    ) -> LLMResult:
        """Run Qwen3.5-4B on the prompt plus the image or video bytes."""
        processor, model = self._load_visual()
        with tempfile.TemporaryDirectory() as tmp:
            content: list[dict[str, str]] = []
            for index, (kind, payload, filename) in enumerate(media):
                if kind != "video":
                    payload, filename = _fit_image(payload, filename)
                path = Path(tmp) / f"media-{index}{_suffix_for(kind, filename)}"
                path.write_bytes(payload)
                if kind == "video":
                    content.append({"type": "video", "video": str(path)})
                else:
                    content.append({"type": "image", "image": str(path)})
            content.append({"type": "text", "text": prompt})
            return self._decode(
                processor,
                model,
                [{"role": "user", "content": content}],
                prompt,
                max_new_tokens,
            )

    def _decode(
        self,
        processor,
        model,
        messages: list[dict],
        prompt: str,
        max_new_tokens: int | None = None,
    ) -> LLMResult:
        """Generate from chat messages already shaped for the processor."""
        try:
            inputs = processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
                enable_thinking=False,
            )
            device = getattr(model, "device", None) or self._device
            if hasattr(inputs, "to") and device is not None:
                inputs = inputs.to(device)
            input_ids = inputs["input_ids"]
            budget = _output_budget(processor, _sequence_width(input_ids), max_new_tokens)
            generated = model.generate(**inputs, max_new_tokens=budget)
            trimmed = [out[len(src) :] for src, out in zip(input_ids, generated, strict=True)]
            text = processor.batch_decode(
                trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]
        except TimeoutError as exc:
            raise InferenceTimeoutError("Qwen3.5-4B inference timed out") from exc
        except FileNotFoundError as exc:
            raise ModelNotFoundError(f"Qwen3.5-4B weights not found: {self.hf_model_id}") from exc
        except Exception as exc:
            raise ModelUnavailableError(f"Qwen3.5-4B model unavailable: {exc}") from exc
        return LLMResult(text=text.strip(), tokens_used=_count_tokens(prompt, text))

    def chat(
        self,
        messages: list[dict],
        context: str | None = None,
        max_new_tokens: int | None = None,
    ) -> LLMResult:
        """Multimodal chat. Data-URL images and videos are shown to the model."""
        text_messages: list[dict] = []
        media: list[tuple[str, bytes, str]] = []
        for message in messages:
            content, parts = extract_inline_media(message.get("content", ""))
            text_messages.append({**message, "content": content})
            media.extend(parts)
        prompt = build_chat_prompt(text_messages, context)
        return self.complete(prompt, media or None, max_new_tokens)

    def extract_triples(self, content: str) -> tuple[list[dict], int]:
        """Reason over document content and return SPO triples."""
        prompt = TRIPLE_EXTRACTION_PROMPT.format(content=content)
        if self.mock:
            snippet = content.strip().split(".")[0][:80] or "document"
            triples = [
                {
                    "subject": snippet,
                    "predicate": "mentions",
                    "object": "extracted-fact",
                    "metadata": {"source": "qwen3.5-4b-base", "confidence": 0.5},
                }
            ]
            tokens = _count_tokens(prompt, json.dumps(triples))
            return triples, tokens
        result = self._generate(prompt)
        return parse_triples_json(result.text), result.tokens_used

    def _generate(self, prompt: str, max_new_tokens: int | None = 256) -> LLMResult:
        """Run text on the same bfloat16 checkpoint used for images and video."""
        processor, model = self._load_visual()
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        return self._decode(processor, model, messages, prompt, max_new_tokens)

    def _load_visual(self):
        """Load Qwen3.5-4B once, in the checkpoint dtype, for text and media."""
        if self._visual_model is not None and self._processor is not None:
            return self._processor, self._visual_model
        from config import export_hf_home

        export_hf_home()
        try:
            import torch
            from transformers import AutoProcessor, Qwen3_5ForConditionalGeneration
        except ImportError as exc:
            raise ModelUnavailableError(
                "Inference needs transformers>=5.3, torch, torchvision, and Pillow. "
                "Install services/llm/requirements-gpu.txt"
            ) from exc
        device = _torch_device()
        if device == "mps":
            _install_mps_convolution_fallback()
        if device == "cpu":
            raise ModelUnavailableError(
                "Qwen3.5-4B bfloat16 needs Metal or CUDA. This process has neither."
            )
        try:
            self._processor = AutoProcessor.from_pretrained(self.hf_model_id)
            model = Qwen3_5ForConditionalGeneration.from_pretrained(
                self.hf_model_id,
                dtype=torch.bfloat16,
                low_cpu_mem_usage=True,
            )
            self._visual_model = model.to(device).eval()
            self._device = device
        except OSError as exc:
            raise ModelNotFoundError(f"Qwen3.5-4B model not found: {self.hf_model_id}") from exc
        except Exception as exc:
            raise ModelUnavailableError(f"Qwen3.5-4B model unavailable: {exc}") from exc
        return self._processor, self._visual_model
