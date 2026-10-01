"""Analytics Service tests: Pearson, loaders, ingest, isolation."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

_SERVICE_ROOT = Path(__file__).resolve().parent
_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "exceptions",
    "base",
    "db",
    "loaders",
    "llm_client",
    "rag_client",
    "pearson",
    "pipeline",
)


def _isolate_service_imports() -> None:
    root_s = str(_SERVICE_ROOT)
    for name in list(sys.modules):
        if name not in _TOP_LEVEL and not any(name.startswith(f"{item}.") for item in _TOP_LEVEL):
            continue
        mod_file = getattr(sys.modules[name], "__file__", None) or ""
        if mod_file and Path(mod_file).resolve().is_relative_to(_SERVICE_ROOT):
            continue
        del sys.modules[name]
    if root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)


_isolate_service_imports()

from exceptions import EmptyFileError, LLMUpstreamError, UnsupportedFileError
from fastapi.testclient import TestClient
from loaders import _load_path, kind_for
from main import app
from pearson import normalize_day, pearson

CSV = "date,sleep_hours,productivity_score\n2026-01-01,6,4\n2026-01-02,8,8\n"


def _infer_ok(**kwargs):
    assert kwargs["user_id"] == "user1"
    return {
        "narrative": "Sleep tracks productivity.",
        "inferred_facts": ["two diary days"],
        "days": [
            {
                "date": "2026-01-01",
                "sleep_hours": 6,
                "productivity_score": 4,
                "meeting_hours": 1,
                "focus_hours": 4,
            },
            {
                "date": "2026-01-02",
                "sleep_hours": 8,
                "productivity_score": 8,
                "meeting_hours": 3,
                "focus_hours": 2,
            },
        ],
    }


def _post(client: TestClient, name: str = "diary.csv", body: bytes = CSV.encode(), **data):
    fields = {"user_id": "user1", "subscription_tier": "premium", **data}
    return client.post(
        "/ingest",
        data=fields,
        files={"file": (name, body, "application/octet-stream")},
        headers={"X-Request-ID": "cid-analytics"},
    )


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


class TestHealthAndCorrelation:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "analytics-service"
        assert "secret" not in str(body).lower()

    def test_generates_request_id(self, client):
        response = client.get("/health")
        assert len(response.headers["X-Request-ID"]) >= 32

    def test_propagates_request_id(self, client):
        response = client.get("/health", headers={"X-Request-ID": "cid-analytics"})
        assert response.headers["X-Request-ID"] == "cid-analytics"


class TestPearson:
    def test_known_r(self):
        r, n, status = pearson([6, 7, 8], [4, 5, 6])
        assert r == 1.0
        assert n == 3
        assert status == "ok"

    def test_insufficient_n(self):
        r, n, status = pearson([6], [4])
        assert r is None
        assert n == 1
        assert status == "insufficient"

    def test_zero_variance(self):
        r, n, status = pearson([7, 7], [4, 9])
        assert r is None
        assert n == 2
        assert status == "insufficient"


class TestLoaders:
    @pytest.mark.parametrize(
        ("name", "kind"),
        [
            ("day.csv", "csv"),
            ("day.xlsx", "xlsx"),
            ("day.docx", "docx"),
            ("cal.ics", "ics"),
            ("page.png", "image"),
            ("page.jpeg", "image"),
            ("page.webp", "image"),
        ],
    )
    def test_kind(self, name, kind):
        assert kind_for(name) == kind

    def test_unsupported(self):
        with pytest.raises(UnsupportedFileError):
            kind_for("notes.pdf")

    @pytest.mark.parametrize("kind", ["csv", "xlsx", "docx", "ics", "image"])
    def test_loader_kind_and_image_ocr_text(self, monkeypatch, kind):
        seen: dict[str, str] = {}

        class FakeLoader:
            def __init__(self, path):
                seen["path"] = path

            def load(self):
                text = "ocr diary page" if kind == "image" else "date,sleep_hours"
                return [SimpleNamespace(page_content=text)]

        def cls(requested):
            seen["kind"] = requested
            return FakeLoader

        monkeypatch.setattr("loaders._loader_cls", cls)
        text = _load_path(kind, "/tmp/upload")
        assert seen["kind"] == kind
        if kind == "image":
            assert text == "ocr diary page"


class TestIngest:
    def test_csv_calls_llm_and_stores(self, client):
        with (
            patch("pipeline.load_upload", return_value=(CSV, b"")) as loaded,
            patch("pipeline.rag_client.excerpts", new_callable=AsyncMock) as search,
            patch("pipeline.llm_client.infer", new_callable=AsyncMock) as infer,
        ):
            search.return_value = "only this user"
            infer.side_effect = _infer_ok
            response = _post(client)
        assert response.status_code == 200
        assert "only this user" in infer.await_args.kwargs["excerpts"]
        body = response.json()
        assert body["rows_upserted"] == 2
        assert body["llm_used"] is True
        assert body["insights"]["narrative"]
        loaded.assert_called_once()
        infer.assert_awaited()
        assert search.await_args.kwargs["user_id"] == "user1"
        view = client.get(
            "/correlations",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        pairs = view.json()["pairs"]
        assert pairs["sleep_productivity"]["status"] == "ok"
        assert pairs["sleep_productivity"]["r"] == 1.0
        assert pairs["sleep_productivity"]["n"] == 2
        assert pairs["meetings_focus"]["n"] == 2
        assert view.json()["narrative"] == "Sleep tracks productivity."
        again = client.get(
            "/correlations",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        assert again.json()["pairs"] == pairs
        insights = client.get(
            "/insights",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        assert insights.json()["llm_used"] is True
        assert insights.json()["narrative"]

    def test_image_sends_bytes_to_llm(self, client):
        with (
            patch("pipeline.load_upload", return_value=("ocr diary page", b"png-bytes")),
            patch("pipeline.rag_client.excerpts", new_callable=AsyncMock, return_value=""),
            patch("pipeline.llm_client.infer", new_callable=AsyncMock) as infer,
        ):
            infer.side_effect = _infer_ok
            response = _post(client, name="page.png", body=b"png-bytes")
        assert response.status_code == 200
        assert infer.await_args.kwargs["image"] == b"png-bytes"
        assert response.json()["llm_used"] is True

    def test_llm_5xx_does_not_write(self, client):
        with (
            patch("pipeline.load_upload", return_value=(CSV, b"")),
            patch("pipeline.rag_client.excerpts", new_callable=AsyncMock, return_value=""),
            patch(
                "pipeline.llm_client.infer",
                new_callable=AsyncMock,
                side_effect=LLMUpstreamError("LLM service HTTP 500"),
            ),
        ):
            failed = _post(client)
        assert failed.status_code == 502
        metrics = client.get(
            "/metrics",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        assert metrics.json()["metrics"] == []

    def test_empty_file_422_skips_llm(self, client):
        with patch("pipeline.llm_client.infer", new_callable=AsyncMock) as infer:
            response = _post(client, body=b"")
        assert response.status_code == 422
        infer.assert_not_awaited()

    def test_unsupported_422_skips_llm(self, client):
        with patch("pipeline.llm_client.infer", new_callable=AsyncMock) as infer:
            response = _post(client, name="notes.pdf", body=b"hello")
        assert response.status_code == 422
        infer.assert_not_awaited()

    def test_loader_empty_text_422(self, client):
        with (
            patch("pipeline.load_upload", side_effect=EmptyFileError("no text")),
            patch("pipeline.llm_client.infer", new_callable=AsyncMock) as infer,
        ):
            response = _post(client, name="day.docx", body=b" ")
        assert response.status_code == 422
        infer.assert_not_awaited()

    def test_free_403(self, client):
        response = _post(client, subscription_tier="free")
        assert response.status_code == 403
        listed = client.get(
            "/correlations",
            params={"user_id": "user1", "subscription_tier": "free"},
        )
        assert listed.status_code == 403

    def test_cross_user_404(self, client):
        with (
            patch("pipeline.load_upload", return_value=(CSV, b"")),
            patch("pipeline.rag_client.excerpts", new_callable=AsyncMock, return_value="x"),
            patch("pipeline.llm_client.infer", new_callable=AsyncMock, side_effect=_infer_ok),
        ):
            created = _post(client)
        assert created.status_code == 200
        metrics = client.get(
            "/metrics",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        metric_id = metrics.json()["metrics"][0]["id"]
        snapshot_id = created.json()["snapshot_id"]
        hidden_metric = client.get(
            f"/metrics/{metric_id}",
            params={"user_id": "user2", "subscription_tier": "premium"},
        )
        hidden_snapshot = client.get(
            f"/snapshots/{snapshot_id}",
            params={"user_id": "user2", "subscription_tier": "premium"},
        )
        own = client.get(
            "/metrics",
            params={"user_id": "user2", "subscription_tier": "premium"},
        )
        assert hidden_metric.status_code == 404
        assert hidden_snapshot.status_code == 404
        assert own.json()["metrics"] == []

    def test_drops_out_of_range_fields(self):
        day = normalize_day(
            {
                "date": "2026-01-03",
                "sleep_hours": 30,
                "productivity_score": 8,
                "meeting_hours": 2,
            }
        )
        assert day is not None
        assert "sleep_hours" not in day
        assert day["productivity_score"] == 8
