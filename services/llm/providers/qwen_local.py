"""Local Qwen3.5-4B provider — base model, full precision, not fine-tuned.

Loads the model in this container when QWEN_MOCK=false. Tests and laptop
dev default to mock so CI does not download ~8 GB weights.
"""

from __future__ import annotations

import json
import re
from typing import Any

from exceptions import InferenceTimeoutError, ModelNotFoundError, ModelUnavailableError
from providers.base import LLMResult

_TOKEN_RE = re.compile(r"\S+")


def _count_tokens(*parts: str) -> int:
    total = 0
    for part in parts:
        total += len(_TOKEN_RE.findall(part or ""))
    return max(1, total)


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
        elif part_type == "image":
            ref = part.get("url") or part.get("data") or part.get("path") or "image"
            chunks.append(f"[image:{ref}]")
        elif part_type == "video":
            ref = part.get("url") or part.get("data") or part.get("path") or "video"
            chunks.append(f"[video:{ref}]")
        else:
            chunks.append(str(part.get("text") or part))
    return " ".join(chunk for chunk in chunks if chunk)


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
    """In-container Qwen3.5-4B base inference (not fine-tuned)."""

    name = "qwen-local-container"

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
        self._model = None
        self._tokenizer = None

    def complete(self, prompt: str) -> LLMResult:
        """Complete a prompt with the base Qwen3.5-4B model."""
        if self.mock:
            text = f"[Qwen3.5-4B base] {prompt.strip()}"
            return LLMResult(text=text, tokens_used=_count_tokens(prompt, text))
        return self._generate(prompt)

    def chat(self, messages: list[dict], context: str | None = None) -> LLMResult:
        """Multimodal chat (text / image / video tags) with optional RAG context."""
        prompt = build_chat_prompt(messages, context)
        return self.complete(prompt)

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

    def _generate(self, prompt: str) -> LLMResult:
        """Run HuggingFace generate; raises domain errors on failure."""
        tokenizer, model = self._load()
        try:
            inputs = tokenizer(prompt, return_tensors="pt")
            outputs = model.generate(**inputs, max_new_tokens=256)
            text = tokenizer.decode(outputs[0], skip_special_tokens=True)
            tokens_used = (
                int(outputs.shape[-1]) if hasattr(outputs, "shape") else _count_tokens(prompt, text)
            )
            return LLMResult(text=text, tokens_used=tokens_used)
        except TimeoutError as exc:
            raise InferenceTimeoutError("Qwen3.5-4B inference timed out") from exc
        except FileNotFoundError as exc:
            raise ModelNotFoundError(f"Qwen3.5-4B weights not found: {self.hf_model_id}") from exc
        except Exception as exc:
            raise ModelUnavailableError(f"Qwen3.5-4B container unavailable: {exc}") from exc

    def _load(self):
        if self._model is not None and self._tokenizer is not None:
            return self._tokenizer, self._model
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ModelUnavailableError(
                "transformers is required when QWEN_MOCK=false. "
                "Install services/llm/requirements-gpu.txt"
            ) from exc
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self.hf_model_id)
            self._model = AutoModelForCausalLM.from_pretrained(self.hf_model_id)
        except OSError as exc:
            raise ModelNotFoundError(f"Qwen3.5-4B model not found: {self.hf_model_id}") from exc
        except Exception as exc:
            raise ModelUnavailableError(f"Qwen3.5-4B container unavailable: {exc}") from exc
        return self._tokenizer, self._model
