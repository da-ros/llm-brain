"""Tests for LLM Service — local Qwen3.5-4B provider, resolver, endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ["QWEN_MOCK"] = "true"
os.environ["QWEN_MODEL_ID"] = "qwen3.5-4b"


class TestConfig:
    """Tests for LLM service configuration."""

    def test_config_defaults(self):
        from config import Settings

        s = Settings()
        assert s.LLM_PORT == 8003
        assert s.QWEN_MODEL_ID == "qwen3.5-4b"
        assert s.QWEN_ADAPTER_PATH is None
        assert s.SERVICE_NAME == "llm-service"


class TestProviderProtocol:
    """G.1 — LLMProvider protocol with mock local Qwen."""

    def test_qwen_local_satisfies_protocol(self):
        from providers.base import LLMProvider
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=True)
        assert isinstance(provider, LLMProvider)

    def test_real_visual_call_passes_the_file_bytes_to_the_model(self):
        from providers.qwen_local import QwenLocalProvider

        png = b"\x89PNG\r\n\x1a\nphoto"
        clip = b"\x00\x00\x00\x18ftypmp42"
        seen: dict = {}

        class _Inputs(dict):
            def to(self, _device):
                return self

        class _Processor:
            def apply_chat_template(self, messages, **_kwargs):
                content = messages[0]["content"]
                seen["image"] = Path(content[0]["image"]).read_bytes()
                seen["video"] = content[1]["video"]
                seen["image_suffix"] = Path(content[0]["image"]).suffix
                seen["prompt"] = content[2]["text"]
                seen["thinking"] = _kwargs.get("enable_thinking")
                seen["sample"] = _kwargs.get("do_sample_frames")
                return _Inputs(input_ids=[[1, 2, 3]])

            def batch_decode(self, _ids, **_kwargs):
                return ["A red receipt on a table."]

        class _Model:
            device = "cpu"

            def generate(self, **_kwargs):
                return [[1, 2, 3, 9]]

        def _frames(path, **_kwargs):
            seen["decoded"] = Path(path).read_bytes()
            seen["backend"] = _kwargs.get("backend")
            import numpy as np

            return np.zeros((8, 4, 4, 3), dtype="uint8"), None

        provider = QwenLocalProvider(mock=False)
        with (
            patch.object(provider, "_load_visual", return_value=(_Processor(), _Model())),
            patch("transformers.video_utils.load_video", side_effect=_frames),
        ):
            result = provider.complete(
                "What is this?",
                media=[("image", png, "photo.jpg"), ("video", clip, "clip.mov")],
            )
        assert result.text == "A red receipt on a table."
        assert seen["image"] == png
        assert seen["decoded"] == clip
        assert seen["backend"] == "pyav"
        assert seen["video"].shape == (8, 4, 4, 3)
        assert seen["image_suffix"] == ".jpg"
        assert seen["prompt"] == "What is this?"
        assert seen["thinking"] is False
        assert seen["sample"] is False

    def test_webm_is_shown_to_the_model_as_mp4(self):
        import subprocess

        from providers.qwen_local import QwenLocalProvider

        clip = b"webm-bytes"
        seen: dict = {}

        class _Inputs(dict):
            def to(self, _device):
                return self

        class _Processor:
            def apply_chat_template(self, messages, **_kwargs):
                seen["frames"] = messages[0]["content"][0]["video"]
                return _Inputs(input_ids=[[1]])

            def batch_decode(self, _ids, **_kwargs):
                return ["A short clip."]

        class _Model:
            device = "cpu"

            def generate(self, **_kwargs):
                return [[1, 2]]

        def _transcode(cmd, **_kwargs):
            Path(cmd[-1]).write_bytes(b"mp4-bytes")
            return subprocess.CompletedProcess(cmd, 0)

        def _frames(path, **_kwargs):
            seen["decoded"] = Path(path).read_bytes()
            import numpy as np

            return np.zeros((8, 4, 4, 3), dtype="uint8"), None

        provider = QwenLocalProvider(mock=False)
        with (
            patch.object(provider, "_load_visual", return_value=(_Processor(), _Model())),
            patch("providers.qwen_local.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("providers.qwen_local.subprocess.run", side_effect=_transcode),
            patch("transformers.video_utils.load_video", side_effect=_frames),
        ):
            result = provider.complete("What happens?", media=[("video", clip, "clip.webm")])
        assert result.text == "A short clip."
        assert seen["decoded"] == b"mp4-bytes"
        assert seen["frames"].shape[0] == 8

    def test_mpeg_is_shown_to_the_model_as_mp4(self, tmp_path):
        import subprocess

        from providers.qwen_local import _video_for_model

        source = tmp_path / "recap.mpeg"
        source.write_bytes(b"mpeg-bytes")

        def _transcode(cmd, **_kwargs):
            Path(cmd[-1]).write_bytes(b"mp4-bytes")
            return subprocess.CompletedProcess(cmd, 0)

        with (
            patch("providers.qwen_local.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("providers.qwen_local.subprocess.run", side_effect=_transcode) as run,
        ):
            shown = _video_for_model(source)
        assert shown.suffix == ".mp4"
        assert shown.read_bytes() == b"mp4-bytes"
        assert run.call_args.args[0][-1].endswith("recap.mp4")

    def test_complete_returns_tokens(self):
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=True)
        result = provider.complete("¿Cuándo debo tomar la medicina?")
        assert result.text.startswith("[Qwen3.5-4B base]")
        assert result.tokens_used > 0

    def test_chat_with_context_and_multimodal(self):
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=True)
        result = provider.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is on this photo?"},
                        {"type": "image", "url": "s3://receta.png"},
                    ],
                }
            ],
            context="Receta: Ibuprofeno 400mg",
        )
        assert "Ibuprofeno" in result.text
        assert "[image:" in result.text
        assert result.tokens_used > 0

    def test_chat_data_url_image_is_the_file_not_the_base64_text(self):
        import base64
        import hashlib

        from providers.qwen_local import QwenLocalProvider

        png = b"\x89PNG\r\n\x1a\nphoto"
        encoded = base64.b64encode(png).decode("ascii")
        provider = QwenLocalProvider(mock=True)
        result = provider.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Is this a scam?"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:application/octet-stream;base64,{encoded}"},
                        },
                    ],
                }
            ]
        )
        assert "Is this a scam?" in result.text
        assert hashlib.sha256(png).hexdigest() in result.text
        assert encoded not in result.text
        assert "image sha256=" in result.text

    def test_extraction_prompt_asks_for_the_event(self):
        from providers.qwen_local import TRIPLE_EXTRACTION_PROMPT

        assert "what happened" in TRIPLE_EXTRACTION_PROMPT
        assert "Do not emit a fact that only says something is a person" in TRIPLE_EXTRACTION_PROMPT
        assert "Every person, place, date, time, and thing" not in TRIPLE_EXTRACTION_PROMPT

    def test_extract_triples_mock(self):
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=True)
        triples, tokens = provider.extract_triples("Ibuprofeno trata el dolor.")
        assert triples
        assert triples[0]["subject"]
        assert triples[0]["predicate"]
        assert triples[0]["object"]
        assert tokens > 0

    def test_parse_triples_json(self):
        from providers.qwen_local import parse_triples_json

        raw = '[{"subject": "Ibuprofeno", "predicate": "trata", "object": "dolor"}]'
        triples = parse_triples_json(raw)
        assert triples[0]["object"] == "dolor"

    def test_clipped_list_keeps_finished_triples(self):
        from providers.qwen_local import parse_triples_json

        raw = (
            '[{"subject": "Nora", "predicate": "lives in", "object": "Bellwater"},'
            '{"subject": "Pixel", "predicate": "species"'
        )
        triples = parse_triples_json(raw)
        assert len(triples) == 1
        assert triples[0]["object"] == "Bellwater"

    def test_extract_lets_the_model_finish_the_list(self):
        from unittest.mock import MagicMock

        from providers.base import LLMResult
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=False)
        provider._generate = MagicMock(
            return_value=LLMResult(
                text='[{"subject": "Nora", "predicate": "lives in", "object": "Bellwater"}]',
                tokens_used=12,
            )
        )
        triples, tokens = provider.extract_triples("A note about Nora.")
        assert provider._generate.call_args.kwargs["max_new_tokens"] is None
        assert triples[0]["object"] == "Bellwater"
        assert tokens == 12


class TestProviderResolver:
    """G.2 — resolver selects the same base Qwen for free and premium."""

    def test_premium_resolves_to_qwen_local(self):
        from providers.qwen_local import QwenLocalProvider
        from providers.resolver import get_provider

        provider = get_provider("premium")
        assert isinstance(provider, QwenLocalProvider)
        assert provider.mock is True
        assert provider.model_id == "qwen3.5-4b"

    def test_free_resolves_to_same_base_model(self):
        from providers.qwen_local import QwenLocalProvider
        from providers.resolver import get_provider

        provider = get_provider("free")
        assert isinstance(provider, QwenLocalProvider)
        assert provider.model_id == "qwen3.5-4b"
        assert provider.adapter_path is None

    def test_unknown_tier_raises(self):
        from providers.resolver import get_provider

        with pytest.raises(ValueError, match="Unsupported subscription tier"):
            get_provider("unknown")


class TestHealthEndpoint:
    def test_health_reports_configured_backend(self):
        from config import get_settings
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        settings = get_settings()
        backend = settings.LLM_BACKEND.strip().lower()
        expected_provider = (
            "mock"
            if settings.QWEN_MOCK
            else ("ollama" if backend in {"ollama", "ollama_local"} else "qwen-local")
        )
        expected_model = (
            settings.OLLAMA_MODEL if expected_provider == "ollama" else settings.QWEN_MODEL_ID
        )
        assert data["status"] == "ok"
        assert data["service"] == "llm-service"
        assert data["backend"] == backend
        assert data["provider"] == expected_provider
        assert data["device"] == settings.QWEN_DEVICE
        assert data["model"] == expected_model
        assert "api_key" not in data
        assert "secret" not in data


class TestGenerateEndpoint:
    """G.3 — POST /generate with mocked local Qwen3.5-4B."""

    def test_generate_returns_response_and_tokens(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/generate",
            json={"prompt": "¿Cuándo debo tomar la medicina?", "user_id": "user-123"},
            headers={"X-Request-ID": "abc-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert isinstance(data["tokens_used"], int)
        assert data["tokens_used"] > 0
        assert response.headers.get("X-Request-ID") == "abc-123"

    def test_generate_missing_prompt_returns_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/generate", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_generate_empty_prompt_returns_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/generate", json={"prompt": "   ", "user_id": "u1"})
        assert response.status_code == 400

    def test_generate_image_bytes_are_shown_to_the_model(self):
        import base64
        import hashlib

        from fastapi.testclient import TestClient
        from main import app

        png = b"\x89PNG\r\n\x1a\nphoto"
        client = TestClient(app)
        response = client.post(
            "/generate",
            json={
                "prompt": "What is this?",
                "user_id": "u1",
                "media": [
                    {"kind": "image", "content_base64": base64.b64encode(png).decode("ascii")}
                ],
            },
        )
        assert response.status_code == 200
        assert hashlib.sha256(png).hexdigest() in response.json()["response"]
        assert "image sha256=" in response.json()["response"]

    def test_generate_free_tier_uses_base_model(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/generate",
            json={"prompt": "hello", "user_id": "u1", "tier": "free"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["response"].startswith("[Qwen3.5-4B base]")
        assert "hello" in data["response"]
        assert data["tokens_used"] > 0

    def test_generate_timeout_returns_504(self):
        from fastapi.testclient import TestClient
        from main import app
        from providers.qwen_local import QwenLocalProvider

        def boom(self, prompt: str):
            raise TimeoutError("slow")

        with patch.object(QwenLocalProvider, "complete", boom):
            client = TestClient(app)
            response = client.post(
                "/generate",
                json={"prompt": "hello", "user_id": "u1"},
            )
        assert response.status_code == 504

    def test_generate_unavailable_returns_500(self):
        from exceptions import ModelUnavailableError
        from fastapi.testclient import TestClient
        from main import app
        from providers.qwen_local import QwenLocalProvider

        def boom(self, prompt: str):
            raise ModelUnavailableError("Qwen3.5-4B container unavailable")

        with patch.object(QwenLocalProvider, "complete", boom):
            client = TestClient(app)
            response = client.post(
                "/generate",
                json={"prompt": "hello", "user_id": "u1"},
            )
        assert response.status_code == 500


class TestChatEndpoint:
    """G.4 — POST /chat with mocked local Qwen3.5-4B."""

    def test_chat_returns_response_and_tokens(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "¿Qué debo comprar esta semana?"}],
                "context": "Receta: Ibuprofeno 400mg, 3 veces al día",
                "user_id": "user-123",
            },
            headers={"X-Request-ID": "def-456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["tokens_used"] > 0
        assert "Ibuprofeno" in data["response"]

    def test_chat_missing_messages_returns_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/chat", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_chat_free_tier_uses_base_model(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "user_id": "u1",
                "tier": "free",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["response"].startswith("[Qwen3.5-4B base]")
        assert "hello" in data["response"]
        assert data["tokens_used"] > 0


class TestExtractEndpoint:
    def test_extract_returns_triples(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/extract",
            json={"content": "Ibuprofeno trata el dolor.", "user_id": "user-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["triples"]
        assert data["tokens_used"] > 0
        assert "subject" in data["triples"][0]


def test_settings_cache_reset():
    from config import clear_settings_cache, get_settings

    clear_settings_cache()
    s = get_settings()
    assert s.QWEN_MODEL_ID == "qwen3.5-4b"


# ── Ollama provider (Linux backend) ──────────────────────────────


class TestOllamaProvider:
    """LLM_BACKEND=ollama — HTTP provider with mocked Ollama responses."""

    def test_ollama_satisfies_protocol(self):
        from providers.base import LLMProvider
        from providers.ollama_local import OllamaProvider

        provider = OllamaProvider(mock=True)
        assert isinstance(provider, LLMProvider)

    def test_mock_complete_matches_qwen_local_text(self):
        from providers.ollama_local import OllamaProvider

        provider = OllamaProvider(mock=True)
        result = provider.complete("hola")
        assert result.text.startswith("[Qwen3.5-4B base]")
        assert "hola" in result.text
        assert result.tokens_used > 0

    def test_mock_chat_with_image_media(self):
        import base64
        import hashlib

        from providers.ollama_local import OllamaProvider

        png = b"\x89PNG\r\n\x1a\nphoto"
        encoded = base64.b64encode(png).decode("ascii")
        provider = OllamaProvider(mock=True)
        result = provider.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is this?"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ]
        )
        assert "What is this?" in result.text
        # Mock path with inline media shows the decoded sha, not the base64.
        assert hashlib.sha256(png).hexdigest() in result.text
        assert encoded not in result.text

    def test_mock_extract_triples(self):
        from providers.ollama_local import OllamaProvider

        provider = OllamaProvider(mock=True)
        triples, tokens = provider.extract_triples("Ibuprofeno trata el dolor.")
        assert triples
        assert triples[0]["subject"]
        assert tokens > 0

    @staticmethod
    def _fake_ollama(handler):
        """Patch httpx.Client so OllamaProvider talks to ``handler`` instead.

        Each _post opens (and closes) its own client, so the patch builds a
        fresh client per call instead of reusing one closed instance.
        """
        import httpx

        original_client = httpx.Client
        return patch.object(
            httpx,
            "Client",
            side_effect=lambda *args, **kwargs: original_client(
                transport=httpx.MockTransport(handler)
            ),
        )

    def test_complete_posts_to_ollama_and_decodes(self):
        import json as _json

        import httpx
        from providers.ollama_local import OllamaProvider

        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = request.read()
            return httpx.Response(
                200,
                json={
                    "message": {"role": "assistant", "content": "  respuesta  "},
                    "eval_count": 42,
                },
            )

        provider = OllamaProvider(mock=False, model="qwen3.5:4b", url="http://ollama.test:11434")
        with self._fake_ollama(handler):
            result = provider.complete("hola", max_new_tokens=64)
        assert result.text == "respuesta"
        assert result.tokens_used == 42
        assert captured["url"] == "http://ollama.test:11434/api/chat"
        body = _json.loads(captured["body"])
        assert body["model"] == "qwen3.5:4b"
        assert body["options"] == {"num_predict": 64}
        assert body["messages"][0]["content"] == "hola"

    def test_chat_sends_images_and_context(self):
        import base64
        import json as _json

        import httpx
        from providers.ollama_local import OllamaProvider

        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = _json.loads(request.read())
            return httpx.Response(200, json={"message": {"content": "ok"}, "eval_count": 1})

        provider = OllamaProvider(mock=False)
        png = b"\x89PNG\r\n\x1a\nphoto"
        with self._fake_ollama(handler):
            provider.chat(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "mira esto"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64," + base64.b64encode(png).decode()
                                },
                            },
                        ],
                    }
                ],
                context="Receta: Ibuprofeno",
            )
        messages = captured["body"]["messages"]
        assert messages[0]["role"] == "system"
        assert "Ibuprofeno" in messages[0]["content"]
        assert messages[1]["images"] == [base64.b64encode(png).decode()]
        assert "mira esto" in messages[1]["content"]

    def test_video_degrades_to_text_marker(self):
        import json as _json

        import httpx
        from providers.ollama_local import OllamaProvider

        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = _json.loads(request.read())
            return httpx.Response(200, json={"message": {"content": "ok"}, "eval_count": 1})

        provider = OllamaProvider(mock=False)
        with self._fake_ollama(handler):
            provider.chat(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "que hay?"},
                            {
                                "type": "video_url",
                                "video_url": {"url": "data:video/mp4;base64,AAAA"},
                            },
                        ],
                    }
                ]
            )
        entry = captured["body"]["messages"][0]
        assert "[video]" in entry["content"]
        assert "images" not in entry

    def test_extract_triples_uses_json_format(self):
        import json as _json

        import httpx
        from providers.ollama_local import OllamaProvider

        captured: dict = {}
        payload = [{"subject": "Ibuprofeno", "predicate": "trata", "object": "dolor"}]

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = _json.loads(request.read())
            return httpx.Response(
                200, json={"message": {"content": _json.dumps(payload)}, "eval_count": 10}
            )

        provider = OllamaProvider(mock=False)
        with self._fake_ollama(handler):
            triples, tokens = provider.extract_triples("Ibuprofeno trata el dolor.")
        assert captured["body"]["format"] == "json"
        assert captured["body"]["options"]["num_predict"] == -1
        assert triples[0]["object"] == "dolor"
        assert tokens == 10

    def test_payloads_disable_think_by_default(self):
        import json as _json

        import httpx
        from providers.ollama_local import OllamaProvider

        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(_json.loads(request.read()))
            return httpx.Response(200, json={"message": {"content": "ok"}, "eval_count": 1})

        provider = OllamaProvider(mock=False)
        with self._fake_ollama(handler):
            provider.complete("hola")
            provider.chat([{"role": "user", "content": "hola"}])
            provider.extract_triples("Ibuprofeno trata el dolor.")
        assert len(bodies) == 3
        for body in bodies:
            assert body["think"] is False

    def test_think_enabled_propagates_to_payload(self):
        import json as _json

        import httpx
        from providers.ollama_local import OllamaProvider

        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = _json.loads(request.read())
            return httpx.Response(200, json={"message": {"content": "ok"}, "eval_count": 1})

        provider = OllamaProvider(mock=False, think=True)
        with self._fake_ollama(handler):
            provider.complete("hola")
        assert captured["body"]["think"] is True

    def test_server_down_raises_model_not_found(self):
        import httpx
        from exceptions import ModelNotFoundError
        from providers.ollama_local import OllamaProvider

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        provider = OllamaProvider(mock=False, url="http://127.0.0.1:1")
        with self._fake_ollama(handler), pytest.raises(ModelNotFoundError, match="ollama serve"):
            provider.complete("hola")

    def test_missing_model_raises_model_not_found(self):
        import httpx
        from exceptions import ModelNotFoundError
        from providers.ollama_local import OllamaProvider

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "nf"})

        provider = OllamaProvider(mock=False, model="nope:1b")
        with self._fake_ollama(handler), pytest.raises(ModelNotFoundError, match="ollama pull"):
            provider.complete("hola")

    def test_timeout_raises_inference_timeout(self):
        import httpx
        from exceptions import InferenceTimeoutError
        from providers.ollama_local import OllamaProvider

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("too slow", request=request)

        provider = OllamaProvider(mock=False, timeout_seconds=0.5)
        with self._fake_ollama(handler), pytest.raises(InferenceTimeoutError):
            provider.complete("hola")


# ── Resolver backend selection (LLM_BACKEND) ─────────────────────


class TestResolverBackend:
    """LLM_BACKEND picks the provider; QWEN_MOCK still wins over any backend."""

    def _fresh(self):
        import providers.resolver as resolver
        from config import clear_settings_cache

        clear_settings_cache()
        resolver._provider = None
        return resolver

    def test_mock_wins_over_ollama_backend(self):
        resolver = self._fresh()
        with patch.dict(os.environ, {"LLM_BACKEND": "ollama", "QWEN_MOCK": "true"}):
            provider = resolver.get_provider("premium")
        from providers.qwen_local import QwenLocalProvider

        assert isinstance(provider, QwenLocalProvider)
        assert provider.mock is True

    def test_ollama_backend_builds_ollama_provider(self):
        resolver = self._fresh()
        with patch.dict(
            os.environ,
            {"LLM_BACKEND": "ollama", "QWEN_MOCK": "false", "OLLAMA_MODEL": "qwen3.5:4b"},
        ):
            provider = resolver.get_provider("premium")
        from providers.ollama_local import OllamaProvider

        assert isinstance(provider, OllamaProvider)
        assert provider.model == "qwen3.5:4b"
        assert provider.mock is False

    def test_qwen_local_backend_builds_qwen_provider(self):
        resolver = self._fresh()
        with patch.dict(os.environ, {"LLM_BACKEND": "qwen_local", "QWEN_MOCK": "false"}):
            provider = resolver.get_provider("free")
        from providers.qwen_local import QwenLocalProvider

        assert isinstance(provider, QwenLocalProvider)

    def test_resolver_passes_ollama_think_setting(self):
        resolver = self._fresh()
        with patch.dict(
            os.environ,
            {
                "LLM_BACKEND": "ollama",
                "QWEN_MOCK": "false",
                "OLLAMA_THINK": "true",
            },
        ):
            provider = resolver.get_provider("premium")
        from providers.ollama_local import OllamaProvider

        assert isinstance(provider, OllamaProvider)
        assert provider.think is True
        assert provider.mock is False

    def test_unknown_backend_raises(self):
        resolver = self._fresh()
        with (
            patch.dict(os.environ, {"LLM_BACKEND": "vllm", "QWEN_MOCK": "false"}),
            pytest.raises(ValueError, match="Unsupported LLM_BACKEND"),
        ):
            resolver.get_provider("premium")

    def test_provider_is_cached_across_calls(self):
        resolver = self._fresh()
        with patch.dict(os.environ, {"LLM_BACKEND": "ollama", "QWEN_MOCK": "true"}):
            first = resolver.get_provider("free")
            second = resolver.get_provider("premium")
        assert first is second

    def test_invalid_tier_still_raises(self):
        resolver = self._fresh()
        with pytest.raises(ValueError, match="Unsupported subscription tier"):
            resolver.get_provider("enterprise")

    def teardown_method(self):
        self._fresh()


# ── Extract endpoint coverage ─────────────────────────────────────


class TestExtractCoverage:
    def test_extract_empty_content(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/extract", json={"content": "", "user_id": "u1"})
        assert response.status_code == 400

    def test_extract_whitespace_content(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/extract", json={"content": "   ", "user_id": "u1"})
        assert response.status_code == 400

    def test_extract_missing_content(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/extract", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_extract_invalid_tier(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/extract",
            json={"content": "test content", "user_id": "u1", "tier": "invalid"},
        )
        assert response.status_code == 400


# ── Chat endpoint coverage ────────────────────────────────────────


class TestChatCoverage:
    def test_chat_empty_messages(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/chat", json={"messages": [], "user_id": "u1"})
        assert response.status_code == 400

    def test_chat_missing_messages(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/chat", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_chat_missing_user_id(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        assert response.status_code == 400

    def test_chat_invalid_tier(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "user_id": "u1",
                "tier": "invalid",
            },
        )
        assert response.status_code == 400

    def test_chat_success(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "user_id": "u1",
            },
        )
        assert response.status_code == 200
        assert "response" in response.json()

    def test_chat_with_context(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "user_id": "u1",
                "context": "some RAG context",
            },
        )
        assert response.status_code == 200
