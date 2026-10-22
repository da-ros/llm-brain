"""Tests for ETL Service — LangChain loaders, LLM extraction, distill, Kafka job."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class FakeDoc:
    def __init__(self, page_content: str, metadata: dict | None = None) -> None:
        self.page_content = page_content
        self.metadata = metadata or {}


class BuiltinTextLoader:
    """Stand-in for LangChain TextLoader so unit tests do not need the package."""

    def __init__(self, file_path: str, autodetect_encoding: bool = True) -> None:
        self.file_path = file_path

    def load(self):
        from pathlib import Path

        text = Path(self.file_path).read_text(encoding="utf-8")
        return [FakeDoc(text, {"source": self.file_path})]


class FakeExtractor:
    def __init__(self, triples: list[dict] | None = None) -> None:
        self.calls: list[str] = []
        self.triples = triples or [
            {
                "subject": "Patient",
                "predicate": "has",
                "object": "diabetes",
                "metadata": {"confidence": 0.91},
            },
            {
                "subject": "Patient",
                "predicate": "takes",
                "object": "metformin",
                "metadata": {"confidence": 0.88},
            },
        ]

    def extract_triples(self, content: str, *, user_id=None, correlation_id="no-id"):
        self.calls.append(content)
        return list(self.triples)


# --- Triple model ---


class TestTriple:
    def test_to_dict_and_json_line(self):
        from triples import Triple

        triple = Triple(
            subject="Patient",
            predicate="has",
            object="diabetes",
            metadata={"source_file": "receta.pdf"},
        )
        assert triple.to_dict()["subject"] == "Patient"
        parsed = json.loads(triple.to_json_line())
        assert parsed["predicate"] == "has"

    def test_enrich_metadata_fills_required_fields(self):
        from triples import enrich_metadata

        meta = enrich_metadata(
            {"note": "llm"},
            source_file="a.pdf",
            user_id="user-a",
            page=2,
            section="labs",
            confidence=1.5,
        )
        assert meta["source_file"] == "a.pdf"
        assert meta["user_id"] == "user-a"
        assert meta["page"] == 2
        assert meta["section"] == "labs"
        assert meta["timestamp"]
        assert meta["confidence"] == 1.0
        assert meta["note"] == "llm"

    def test_triple_from_llm_skips_incomplete(self):
        from triples import triple_from_llm

        assert triple_from_llm({"subject": "A"}, source_file="x", user_id="u") is None
        built = triple_from_llm(
            {"subject": "Patient", "predicate": "has", "object": "diabetes"},
            source_file="receta.pdf",
            user_id="user1",
            page=1,
        )
        assert built is not None
        assert built.metadata["source_file"] == "receta.pdf"
        assert built.metadata["page"] == 1


# --- Loader selection ---


class TestLoaderSelection:
    def test_select_pdf(self):
        from base import select
        from loaders import PdfLoaderAdapter

        cls = select("ignored.pdf", mime_type="application/pdf")
        assert cls is PdfLoaderAdapter

    def test_select_text(self):
        from base import select

        cls = select("ignored.txt", mime_type="text/plain")
        assert cls.__name__ == "TextLoaderAdapter"

    def test_select_html(self):
        from base import select

        cls = select("ignored.html", mime_type="text/html")
        assert "HTML" in cls.__name__

    def test_select_eml(self):
        from base import select

        cls = select("ignored.eml", mime_type="message/rfc822")
        assert "Email" in cls.__name__

    def test_select_docx(self):
        from base import select

        cls = select(
            "ignored.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert "Word" in cls.__name__

    def test_select_image(self):
        from base import select

        cls = select("ignored.png", mime_type="image/png")
        assert "Image" in cls.__name__

    def test_select_video(self):
        from base import select
        from loaders import VideoFileLoader

        cls = select("ignored.mp4", mime_type="video/mp4")
        assert cls is VideoFileLoader

    def test_select_unsupported(self):
        from base import select
        from exceptions import UnsupportedFileTypeError

        with pytest.raises(UnsupportedFileTypeError):
            select("malware.exe", mime_type="application/x-msdownload")


class TestLoaderWrappers:
    def test_pdf_loader_uses_pypdf_when_text_exists(self):
        from loaders import PdfLoaderAdapter

        docs = [FakeDoc("Patient has diabetes", {"page": 0})]
        fake = MagicMock()
        fake.return_value.load.return_value = docs
        plumber = MagicMock()
        plumber.return_value.load.return_value = [FakeDoc("")]
        ocr = MagicMock()
        with patch("loaders._pdf_loader_classes", return_value=(fake, plumber, ocr)):
            loaded = PdfLoaderAdapter("receta.pdf").load()
        assert loaded[0].page_content.startswith("Patient")

    def test_pdf_falls_back_to_unstructured_ocr_when_empty(self):
        from loaders import PdfLoaderAdapter

        empty = MagicMock()
        empty.return_value.load.return_value = [FakeDoc("   ", {"page": 0})]
        ocr = MagicMock()
        ocr.return_value.load.return_value = [FakeDoc("scanned recipe", {"page": 0})]
        with patch("loaders._pdf_loader_classes", return_value=(empty, empty, ocr)):
            loaded = PdfLoaderAdapter("scan.pdf").load()
        assert loaded[0].page_content == "scanned recipe"

    def test_text_loader_reads_file(self, tmp_path):
        from base import load

        path = tmp_path / "note.txt"
        path.write_text("Alice is a doctor.\n", encoding="utf-8")
        with patch("loaders._text_loader_class", return_value=BuiltinTextLoader):
            documents = load(str(path), mime_type="text/plain")
        assert "Alice" in documents[0].page_content

    def test_html_loader_is_unstructured(self):
        from loaders import UnstructuredHTMLLoaderAdapter

        fake = MagicMock()
        fake.return_value.load.return_value = [FakeDoc("body text")]
        with patch("loaders._html_loader_class", return_value=fake):
            loaded = UnstructuredHTMLLoaderAdapter("page.html").load()
        assert loaded[0].page_content == "body text"

    def test_image_loader_uses_tesseract_ocr(self):
        from loaders import UnstructuredImageLoaderAdapter

        fake = MagicMock()
        fake.return_value.load.return_value = [FakeDoc("Invoice 42")]
        with patch("loaders._image_loader_class", return_value=fake):
            loaded = UnstructuredImageLoaderAdapter("/tmp/photo.png").load()
        fake.assert_called_once_with(
            "/tmp/photo.png",
            strategy="ocr_only",
            languages=["eng", "spa"],
        )
        assert loaded[0].page_content == "Invoice 42"

    def test_video_loader_wraps_unstructured_file_loader(self):
        from loaders import VideoFileLoader

        fake = MagicMock()
        fake.return_value.load.return_value = [FakeDoc("video transcript")]
        with patch("loaders._video_loader_class", return_value=fake):
            loaded = VideoFileLoader("clip.mp4").load()
        assert loaded[0].page_content == "video transcript"


# --- LLM client ---


class TestLLMClient:
    def test_extract_triples_posts_to_llm_service(self):
        from llm_client import LLMServiceClient

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "triples": [
                {"subject": "Patient", "predicate": "has", "object": "diabetes", "metadata": {}}
            ],
            "tokens_used": 12,
        }
        client_cm = MagicMock()
        client_cm.__enter__.return_value.post.return_value = response
        with patch("llm_client.httpx.Client", return_value=client_cm):
            triples = LLMServiceClient(base_url="http://llm-service:8003").extract_triples(
                "Patient has diabetes",
                user_id="user1",
                correlation_id="abc-123",
            )
        assert triples[0]["object"] == "diabetes"
        post = client_cm.__enter__.return_value.post
        post.assert_called_once()
        args, kwargs = post.call_args
        assert args[0] == "http://llm-service:8003/extract"
        assert kwargs["json"]["content"].startswith("Patient")
        assert kwargs["headers"]["X-Request-ID"] == "abc-123"

    def test_describe_image_posts_the_raw_bytes(self):
        import base64

        from llm_client import LLMServiceClient

        png = b"\x89PNG\r\n\x1a\nphoto"
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"response": "A red receipt on a table.", "tokens_used": 8}
        client_cm = MagicMock()
        client_cm.__enter__.return_value.post.return_value = response
        with patch("llm_client.httpx.Client", return_value=client_cm):
            text = LLMServiceClient(base_url="http://llm-service:8003").describe_media(
                png,
                kind="image",
                filename="photo.jpg",
                user_id="user1",
                correlation_id="abc-123",
            )
        assert text == "A red receipt on a table."
        args, kwargs = client_cm.__enter__.return_value.post.call_args
        assert args[0] == "http://llm-service:8003/generate"
        assert kwargs["json"]["media"][0]["kind"] == "image"
        assert kwargs["json"]["media"][0]["filename"] == "photo.jpg"
        assert base64.b64decode(kwargs["json"]["media"][0]["content_base64"]) == png
        assert kwargs["headers"]["X-Request-ID"] == "abc-123"

    def test_extract_triples_timeout(self):
        import httpx
        from exceptions import LLMExtractionError
        from llm_client import LLMServiceClient

        with (
            patch("llm_client.httpx.Client", side_effect=httpx.TimeoutException("t")),
            pytest.raises(LLMExtractionError, match="timeout"),
        ):
            LLMServiceClient().extract_triples("content")

    def test_extract_triples_http_error(self):
        from exceptions import LLMExtractionError
        from llm_client import LLMServiceClient

        response = MagicMock()
        response.status_code = 500
        response.text = "boom"
        client_cm = MagicMock()
        client_cm.__enter__.return_value.post.return_value = response
        with (
            patch("llm_client.httpx.Client", return_value=client_cm),
            pytest.raises(LLMExtractionError, match="500"),
        ):
            LLMServiceClient().extract_triples("content")


# --- Pipeline ---


class TestPipeline:
    def test_distill_writes_jsonl_per_user(self, tmp_path):
        from pipeline import distill

        source = tmp_path / "receta.txt"
        source.write_text("The patient has diabetes and takes metformin.", encoding="utf-8")
        extractor = FakeExtractor()
        with patch("loaders._text_loader_class", return_value=BuiltinTextLoader):
            triples = distill(
                str(source),
                user_id="user-a",
                document_id="doc-1",
                mime_type="text/plain",
                llm_client=extractor,
                output_dir=str(tmp_path / "triples"),
                correlation_id="abc-123",
            )
        assert len(triples) == 2
        assert triples[0].metadata["user_id"] == "user-a"
        assert triples[0].metadata["source_file"] == "receta.txt"
        assert "timestamp" in triples[0].metadata
        out = tmp_path / "triples" / "user-a" / "doc-1.jsonl"
        assert out.exists()
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        row = json.loads(lines[0])
        assert row["subject"] == "Patient"
        assert not (tmp_path / "triples" / "user-b").exists()

    def test_distill_uses_the_original_filename_not_the_temp_path(self, tmp_path):
        from pipeline import distill

        source = tmp_path / "tmpubnut7q8.txt"
        source.write_text("The patient has diabetes and takes metformin.", encoding="utf-8")
        with patch("loaders._text_loader_class", return_value=BuiltinTextLoader):
            triples = distill(
                str(source),
                user_id="user-a",
                document_id="doc-1",
                mime_type="text/plain",
                llm_client=FakeExtractor(),
                output_dir=str(tmp_path / "triples"),
                filename="memories-1.docx",
                write_output=False,
            )
        assert triples[0].metadata["source_file"] == "memories-1.docx"

    def test_image_with_ocr_text_is_extracted_without_a_description(self, tmp_path):
        from pipeline import distill

        source = tmp_path / "photo.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\nphoto")
        extractor = FakeExtractor()

        def describe_media(*_args, **_kwargs):
            raise AssertionError("OCR text should not be sent for a description")

        extractor.describe_media = describe_media
        with patch("pipeline.load", return_value=[FakeDoc("Invoice 42")]):
            distill(
                str(source),
                user_id="user-a",
                document_id="doc-img",
                mime_type="image/png",
                llm_client=extractor,
                output_dir=str(tmp_path / "triples"),
            )
        assert extractor.calls == ["Invoice 42"]

    def test_image_without_ocr_is_described_then_extracted(self, tmp_path):
        from exceptions import CorruptFileError
        from pipeline import distill

        png = b"\x89PNG\r\n\x1a\nphoto"
        source = tmp_path / "photo.png"
        source.write_bytes(png)
        extractor = FakeExtractor()
        seen: dict = {}

        def describe_media(payload, *, kind, filename="", user_id=None, correlation_id="no-id"):
            seen["payload"] = payload
            seen["kind"] = kind
            seen["filename"] = filename
            return "A red receipt on a wooden table."

        extractor.describe_media = describe_media
        with patch(
            "pipeline.load",
            side_effect=CorruptFileError("Loader returned no extractable content"),
        ):
            triples = distill(
                str(source),
                user_id="user-a",
                document_id="doc-img",
                mime_type="image/png",
                llm_client=extractor,
                output_dir=str(tmp_path / "triples"),
            )
        assert seen["payload"] == png
        assert seen["kind"] == "image"
        assert seen["filename"] == "photo.png"
        assert extractor.calls == ["A red receipt on a wooden table."]
        assert len(triples) == 2
        out = tmp_path / "triples" / "user-a" / "doc-img.jsonl"
        assert out.exists()

    def test_video_without_text_is_described_then_extracted(self, tmp_path):
        from exceptions import CorruptFileError
        from pipeline import distill

        clip = b"\x00\x00\x00\x18ftypmp42"
        source = tmp_path / "clip.mov"
        source.write_bytes(clip)
        extractor = FakeExtractor()
        seen: dict = {}

        def describe_media(payload, *, kind, filename="", user_id=None, correlation_id="no-id"):
            seen["payload"] = payload
            seen["kind"] = kind
            seen["filename"] = filename
            return "A person sets a receipt on a table."

        extractor.describe_media = describe_media
        with patch(
            "pipeline.load",
            side_effect=CorruptFileError("Loader returned no extractable content"),
        ):
            triples = distill(
                str(source),
                user_id="user-a",
                document_id="doc-clip",
                mime_type="video/quicktime",
                llm_client=extractor,
                output_dir=str(tmp_path / "triples"),
            )
        assert seen == {
            "payload": clip,
            "kind": "video",
            "filename": "clip.mov",
        }
        assert extractor.calls == ["A person sets a receipt on a table."]
        assert len(triples) == 2

    def test_video_with_transcript_is_extracted_without_a_description(self, tmp_path):
        from pipeline import distill

        source = tmp_path / "clip.mov"
        source.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        extractor = FakeExtractor()

        def describe_media(*_args, **_kwargs):
            raise AssertionError("A transcript should not be sent for a description")

        extractor.describe_media = describe_media
        with patch("pipeline.load", return_value=[FakeDoc("The speaker says invoice 42")]):
            distill(
                str(source),
                user_id="user-a",
                document_id="doc-clip",
                mime_type="video/quicktime",
                llm_client=extractor,
                output_dir=str(tmp_path / "triples"),
            )
        assert extractor.calls == ["The speaker says invoice 42"]

    def test_text_file_without_words_still_fails(self, tmp_path):
        from exceptions import CorruptFileError
        from pipeline import distill

        source = tmp_path / "empty.txt"
        source.write_text("   ", encoding="utf-8")
        with (
            patch(
                "pipeline.load",
                side_effect=CorruptFileError("Loader returned no extractable content"),
            ),
            pytest.raises(CorruptFileError),
        ):
            distill(
                str(source),
                user_id="user-a",
                document_id="doc-empty",
                mime_type="text/plain",
                llm_client=FakeExtractor(),
                write_output=False,
            )

    def test_distill_missing_file(self, tmp_path):
        from pipeline import distill

        with pytest.raises(FileNotFoundError):
            distill(
                str(tmp_path / "missing.txt"),
                user_id="u",
                document_id="d",
                llm_client=FakeExtractor(),
                write_output=False,
            )

    def test_jsonl_writer_isolation(self, tmp_path):
        from jsonl import write_triples
        from triples import Triple

        write_triples(
            [Triple("A", "is", "B", {"user_id": "u1"})],
            user_id="u1",
            document_id="d1",
            output_dir=str(tmp_path),
        )
        write_triples(
            [Triple("C", "is", "D", {"user_id": "u2"})],
            user_id="u2",
            document_id="d1",
            output_dir=str(tmp_path),
        )
        assert (tmp_path / "u1" / "d1.jsonl").exists()
        assert (tmp_path / "u2" / "d1.jsonl").exists()
        u1 = (tmp_path / "u1" / "d1.jsonl").read_text()
        assert "C" not in u1


class TestPdfIntegration:
    def test_upload_pdf_llm_extracts_triples_jsonl(self, tmp_path):
        """E.3 — PDF → LLM triples → JSONL (LangChain loader + LLM mocked)."""
        from pipeline import distill

        pdf = tmp_path / "receta.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        docs = [
            FakeDoc(
                "The patient has diabetes. The patient takes metformin.",
                {"page": 1, "source": "receta.pdf"},
            )
        ]
        extractor = FakeExtractor()
        with patch("pipeline.load", return_value=docs):
            triples = distill(
                str(pdf),
                user_id="user1",
                document_id="corr-pdf",
                mime_type="application/pdf",
                llm_client=extractor,
                output_dir=str(tmp_path / "triples"),
            )
        assert {t.predicate for t in triples} == {"has", "takes"}
        out = tmp_path / "triples" / "user1" / "corr-pdf.jsonl"
        rows = [json.loads(line) for line in out.read_text().splitlines()]
        assert len(rows) == 2
        assert extractor.calls[0].startswith("--- page 1 ---")


class TestKafkaJob:
    def test_process_file_message_success(self, tmp_path):
        from kafka_io import process_file_message

        extractor = FakeExtractor()
        docs = [FakeDoc("Patient has diabetes", {"page": 0, "source": "receta.pdf"})]
        with (
            patch(
                "kafka_io.fetch_file", return_value=(b"%PDF-1.4 x", "receta.pdf", "application/pdf")
            ),
            patch("pipeline.load", return_value=docs),
        ):
            result = process_file_message(
                {
                    "correlation_id": "abc-123",
                    "user_id": "user1",
                    "file_id": "507f1f77bcf86cd799439011",
                    "filename": "receta.pdf",
                    "content_type": "application/pdf",
                },
                llm_client=extractor,
                output_dir=str(tmp_path / "triples"),
                publish=False,
            )
        assert result["status"] == "success"
        assert result["result"]["triples_count"] == 2
        assert (tmp_path / "triples" / "user1" / "abc-123.jsonl").exists()

    def test_process_file_message_corrupt_is_422(self, tmp_path):
        from exceptions import CorruptFileError
        from kafka_io import process_file_message

        with (
            patch(
                "kafka_io.fetch_file",
                return_value=(b"not-a-pdf", "corrupt.pdf", "application/pdf"),
            ),
            patch("pipeline.load", side_effect=CorruptFileError("PDF is corrupted")),
        ):
            result = process_file_message(
                {
                    "correlation_id": "abc-456",
                    "user_id": "user3",
                    "file_id": "507f1f77bcf86cd799439011",
                    "filename": "corrupt.pdf",
                    "content_type": "application/pdf",
                },
                llm_client=FakeExtractor(),
                output_dir=str(tmp_path),
                publish=False,
            )
        assert result["status"] == "error"
        assert result["http_code"] == 422


class TestHealth:
    def test_health_ok_while_idle(self):
        from main import app

        with TestClient(app) as client:
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "etl-service"


class TestSampleCorpus:
    def test_process_100_sample_documents(self, tmp_path):
        """E.4 — >=100 documents, JSONL quality (required fields, per-user path)."""
        from pipeline import distill

        output_dir = tmp_path / "triples"
        extractor = FakeExtractor(
            triples=[
                {
                    "subject": "Patient",
                    "predicate": "has",
                    "object": "diabetes",
                    "metadata": {"confidence": 0.8},
                }
            ]
        )
        with patch("loaders._text_loader_class", return_value=BuiltinTextLoader):
            for index in range(100):
                source = tmp_path / "docs" / f"sample-{index:03d}.txt"
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(
                    f"Sample document {index}. Patient has diabetes and takes metformin.",
                    encoding="utf-8",
                )
                triples = distill(
                    str(source),
                    user_id="corpus-user",
                    document_id=f"doc-{index:03d}",
                    mime_type="text/plain",
                    llm_client=extractor,
                    output_dir=str(output_dir),
                )
                assert len(triples) >= 1
                row_path = output_dir / "corpus-user" / f"doc-{index:03d}.jsonl"
                rows = [
                    json.loads(line) for line in row_path.read_text().splitlines() if line.strip()
                ]
                assert rows
                for row in rows:
                    assert row["subject"]
                    assert row["predicate"]
                    assert row["object"]
                    meta = row["metadata"]
                    assert meta["source_file"].startswith("sample-")
                    assert meta["user_id"] == "corpus-user"
                    assert "timestamp" in meta
                    assert 0.0 <= float(meta["confidence"]) <= 1.0

        produced = list((output_dir / "corpus-user").glob("*.jsonl"))
        assert len(produced) == 100
        assert not (output_dir / "other-user").exists()


class TestNewLoaderKinds:
    """CSV, TSV, Excel, markdown, and ICS — chat attachment types."""

    def test_resolve_maps_new_mimes(self):
        from loaders import (
            CsvLoaderAdapter,
            ExcelLoaderAdapter,
            TsvLoaderAdapter,
            is_supported_mime,
            resolve_loader_class,
        )

        assert resolve_loader_class("text/csv") is CsvLoaderAdapter
        assert resolve_loader_class("text/tab-separated-values") is TsvLoaderAdapter
        assert resolve_loader_class("text/markdown") is not None
        assert resolve_loader_class("text/calendar") is not None
        assert resolve_loader_class("application/vnd.ms-excel") is ExcelLoaderAdapter
        assert (
            resolve_loader_class(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            is ExcelLoaderAdapter
        )
        for mime in ("text/csv", "text/calendar", "text/markdown", "application/vnd.ms-excel"):
            assert is_supported_mime(mime)

    def test_csv_adapter_passes_comma_delimiter(self):
        from loaders import CsvLoaderAdapter

        fake = MagicMock()
        fake.return_value.load.return_value = [FakeDoc("a,b")]
        with patch("loaders._csv_loader_class", return_value=fake):
            docs = CsvLoaderAdapter("/tmp/x.csv").load()
        assert docs[0].page_content == "a,b"
        fake.assert_called_once_with("/tmp/x.csv", csv_args={"delimiter": ","})

    def test_tsv_adapter_passes_tab_delimiter(self):
        from loaders import TsvLoaderAdapter

        fake = MagicMock()
        fake.return_value.load.return_value = [FakeDoc("a\tb")]
        with patch("loaders._csv_loader_class", return_value=fake):
            TsvLoaderAdapter("/tmp/x.tsv").load()
        fake.assert_called_once_with("/tmp/x.tsv", csv_args={"delimiter": "\t"})

    def test_excel_adapter_uses_unstructured_excel_loader(self):
        from loaders import ExcelLoaderAdapter

        fake = MagicMock()
        fake.return_value.load.return_value = [FakeDoc("sheet")]
        with patch("loaders._excel_loader_class", return_value=fake):
            docs = ExcelLoaderAdapter("/tmp/x.xlsx").load()
        assert docs[0].page_content == "sheet"


def _loader_of(text: str):
    class _Loader:
        def __init__(self, file_path: str) -> None:
            self.file_path = file_path

        def load(self):
            return [FakeDoc(text)]

    return _Loader


class TestParseEndpoint:
    """POST /parse — ephemeral text extraction for chat attachments."""

    def test_empty_body_is_422(self):
        from main import app

        with TestClient(app) as client:
            response = client.post("/parse", params={"filename": "a.txt"}, content=b"")
        assert response.status_code == 422

    def test_markdown_returns_text_via_text_loader(self):
        from main import app

        with (
            patch("loaders._text_loader_class", return_value=BuiltinTextLoader),
            TestClient(app) as client,
        ):
            response = client.post(
                "/parse", params={"filename": "notes.md"}, content=b"hello markdown"
            )
        assert response.status_code == 200
        body = response.json()
        assert body["mime"] == "text/markdown"
        assert "hello markdown" in body["text"]

    def test_image_ocr_text_is_returned(self):
        from main import app

        png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
        with (
            patch("main.select", return_value=_loader_of("Invoice 42")),
            TestClient(app) as client,
        ):
            response = client.post("/parse", params={"filename": "photo.png"}, content=png)
        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "Invoice 42"
        assert body["show_bytes"] is False

    def test_image_loader_crash_asks_to_show_the_bytes(self):
        from exceptions import LoaderError
        from main import app

        class _Boom:
            def __init__(self, file_path: str) -> None:
                self.file_path = file_path

            def load(self):
                raise LoaderError("UnstructuredImageLoader failed: No module named 'pi_heif'")

        png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
        with patch("main.select", return_value=_Boom), TestClient(app) as client:
            response = client.post("/parse", params={"filename": "photo.png"}, content=png)
        assert response.status_code == 200
        body = response.json()
        assert body["text"] == ""
        assert body["mime"] == "image/png"
        assert body["show_bytes"] is True

    def test_image_without_text_asks_to_show_the_bytes(self):
        from main import app

        png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
        with (
            patch("main.select", return_value=_loader_of("")),
            TestClient(app) as client,
        ):
            response = client.post("/parse", params={"filename": "photo.png"}, content=png)
        assert response.status_code == 200
        body = response.json()
        assert body["text"] == ""
        assert body["mime"] == "image/png"
        assert body["show_bytes"] is True

    def test_short_video_without_text_asks_to_show_the_bytes(self):
        from main import app

        clip = b"\x00\x00\x00\x18ftypmp42"
        with (
            patch("main.select", return_value=_loader_of("")),
            TestClient(app) as client,
        ):
            response = client.post("/parse", params={"filename": "clip.mp4"}, content=clip)
        assert response.status_code == 200
        body = response.json()
        assert body["mime"] == "video/mp4"
        assert body["show_bytes"] is True

    def test_unsupported_type_is_422(self):
        from main import app

        with TestClient(app) as client:
            response = client.post("/parse", params={"filename": "data.zip"}, content=b"PK\x03\x04")
        assert response.status_code == 422

    def test_loader_crash_is_clean_422(self):
        from main import app

        with (
            patch("loaders._text_loader_class", side_effect=RuntimeError("boom")),
            TestClient(app) as client,
        ):
            response = client.post("/parse", params={"filename": "a.txt"}, content=b"data")
        assert response.status_code == 422
        assert response.json()["detail"] == "Could not read that file"
