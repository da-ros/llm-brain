"""Ollama provider — local Ollama server over HTTP (Linux default backend).

QWEN_MOCK=true short-circuits to the same mock text as QwenLocalProvider.
CI and unit tests stay on that path and never open a socket.
"""

from __future__ import annotations

import base64
import hashlib
import json

import httpx
from exceptions import InferenceTimeoutError, ModelNotFoundError, ModelUnavailableError
from providers.base import LLMResult
from providers.qwen_local import (
    TRIPLE_EXTRACTION_PROMPT,
    _count_tokens,
    _media_parts,
    build_chat_prompt,
    extract_inline_media,
    flatten_content,
    parse_triples_json,
)


class OllamaProvider:
    """Chat/complete against a local Ollama server (llama.cpp runtime)."""

    name = "ollama"

    def __init__(
        self,
        model: str = "qwen3.5:4b",
        url: str = "http://127.0.0.1:11434",
        mock: bool = True,
        timeout_seconds: float = 600.0,
        think: bool = False,
    ) -> None:
        self.model = model
        self.url = url.rstrip("/")
        self.mock = mock
        self.timeout_seconds = timeout_seconds
        self.think = think

    # ── mock ─────────────────────────────────────────────────────

    def _mock_result(self, prompt: str, media: list[tuple] | None = None) -> LLMResult:
        text = f"[Qwen3.5-4B base] {prompt.strip()}"
        if media:
            shown = "; ".join(
                f"{kind} sha256={hashlib.sha256(payload).hexdigest()}"
                for kind, payload, _filename in media
            )
            text = f"{text}\nShown: {shown}"
        return LLMResult(text=text, tokens_used=_count_tokens(prompt, text))

    # ── HTTP core ───────────────────────────────────────────────

    def _post(self, path: str, payload: dict) -> dict:
        """POST to the Ollama server and return its JSON body."""
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.url}{path}", json=payload)
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError(
                f"Ollama inference timed out after {self.timeout_seconds}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelNotFoundError(
                f"Ollama server not reachable at {self.url}. Is `ollama serve` running? ({exc})"
            ) from exc
        if response.status_code == 404:
            raise ModelNotFoundError(
                f"Ollama model '{self.model}' not found. Run `ollama pull {self.model}`."
            )
        if response.status_code != 200:
            raise ModelUnavailableError(
                f"Ollama error {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ModelUnavailableError("Ollama returned a non-JSON response") from exc

    def _chat_payload(
        self, messages: list[dict], context: str | None, max_new_tokens: int | None
    ) -> dict:
        """Map chat messages to the Ollama /api/chat schema."""
        ollama_messages: list[dict] = []
        if context:
            ollama_messages.append({"role": "system", "content": f"Context:\n{context}\n"})
        for message in messages:
            content, media = extract_inline_media(message.get("content", ""))
            entry: dict = {
                "role": message.get("role", "user"),
                "content": flatten_content(content),
            }
            images: list[str] = []
            for kind, payload, _filename in media:
                if kind == "image":
                    images.append(base64.b64encode(payload).decode("ascii"))
                else:
                    # Ollama has no video input — degrade to a text marker.
                    entry["content"] = f"{entry['content']} [video]".strip()
            if images:
                entry["images"] = images
            ollama_messages.append(entry)
        payload: dict = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "think": self.think,
        }
        if max_new_tokens is not None:
            payload["options"] = {"num_predict": max_new_tokens}
        return payload

    def _decode_response(self, data: dict, prompt: str) -> LLMResult:
        text = str(data.get("message", {}).get("content", "")).strip()
        tokens = data.get("eval_count")
        if not isinstance(tokens, int) or tokens < 1:
            tokens = _count_tokens(prompt, text)
        return LLMResult(text=text, tokens_used=tokens)

    # ── public API ──────────────────────────────────────────────

    def complete(
        self,
        prompt: str,
        media: list[tuple] | None = None,
        max_new_tokens: int | None = None,
    ) -> LLMResult:
        """Complete a prompt. media items are (kind, file bytes, filename)."""
        parts = _media_parts(media)
        if self.mock:
            return self._mock_result(prompt, parts)
        content: list[dict] = []
        images: list[str] = []
        for kind, payload, _filename in parts:
            if kind == "image":
                images.append(base64.b64encode(payload).decode("ascii"))
            else:
                content.append({"type": "text", "text": "[video]"})
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": flatten_content(content)}]
        if images:
            messages[0]["images"] = images
        data = self._post(
            "/api/chat",
            {"model": self.model, "messages": messages, "stream": False, "think": self.think}
            | ({"options": {"num_predict": max_new_tokens}} if max_new_tokens else {}),
        )
        return self._decode_response(data, prompt)

    def chat(
        self,
        messages: list[dict],
        context: str | None = None,
        max_new_tokens: int | None = None,
    ) -> LLMResult:
        """Multimodal chat. Data-URL images go to Ollama; videos degrade to text."""
        text_messages: list[dict] = []
        media: list[tuple[str, bytes, str]] = []
        for message in messages:
            content, parts = extract_inline_media(message.get("content", ""))
            text_messages.append({**message, "content": content})
            media.extend(parts)
        prompt = build_chat_prompt(text_messages, context)
        if self.mock:
            return self._mock_result(prompt, media or None)
        data = self._post("/api/chat", self._chat_payload(messages, context, max_new_tokens))
        return self._decode_response(data, prompt)

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
            return triples, _count_tokens(prompt, json.dumps(triples))
        data = self._post(
            "/api/chat",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": self.think,
                "format": "json",
                # -1 lets the list finish. 1024 cut a real note off mid-array.
                "options": {"num_predict": -1},
            },
        )
        result = self._decode_response(data, prompt)
        return parse_triples_json(result.text), result.tokens_used
