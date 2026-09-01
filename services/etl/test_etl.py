"""Tests for ETL Service — Parsers, Pipeline, and Triple Extraction."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add services/etl to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "etl"))

from services.etl.triples import Triple, extract_triples
from services.etl.base import DocumentParser
from services.etl.parsers.pdf import PdfParser
from services.etl.parsers.html import HtmlParser
from services.etl.parsers.eml import EmlParser
from services.etl.parsers.ocr import OcrParser
from services.etl.pipeline import distill, get_parser, save_triples


# --- Triple Extraction Tests ---


class TestTripleExtraction:
    """Tests for rule-based triple extraction."""

    def test_extract_is_pattern(self):
        """Test extraction of 'X is Y' pattern."""
        text = "Alice is a doctor"
        triples = extract_triples(text)

        assert len(triples) > 0
        assert any(
            t.predicate == "is" and "Alice" in t.subject for t in triples
        )

    def test_extract_has_pattern(self):
        """Test extraction of 'X has Y' pattern."""
        text = "The patient has diabetes"
        triples = extract_triples(text)

        assert len(triples) > 0
        assert any(
            t.predicate == "has" and "diabetes" in t.object for t in triples
        )

    def test_extract_takes_pattern(self):
        """Test extraction of 'X takes Y' pattern."""
        text = "John takes metformin"
        triples = extract_triples(text)

        assert len(triples) > 0
        assert any(
            t.predicate == "takes" and "metformin" in t.object for t in triples
        )

    def test_triple_to_dict(self):
        """Test triple serialization to dict."""
        triple = Triple(
            subject="Patient",
            predicate="has",
            object="diabetes",
            metadata={"source_file": "test.pdf"},
        )

        d = triple.to_dict()
        assert d["subject"] == "Patient"
        assert d["predicate"] == "has"
        assert d["object"] == "diabetes"
        assert d["metadata"]["source_file"] == "test.pdf"

    def test_triple_to_json_line(self):
        """Test triple serialization to JSON line."""
        triple = Triple(
            subject="Patient",
            predicate="has",
            object="diabetes",
        )

        json_line = triple.to_json_line()
        parsed = json.loads(json_line)

        assert parsed["subject"] == "Patient"
        assert parsed["predicate"] == "has"
        assert parsed["object"] == "diabetes"


# --- Parser Protocol Tests ---


class TestDocumentParser:
    """Tests for DocumentParser protocol."""

    def test_pdf_parser_supports(self):
        """Test PDF parser recognizes PDF files."""
        parser = PdfParser()
        assert parser.supports("document.pdf") is True
        assert parser.supports("document.txt") is False

    def test_html_parser_supports(self):
        """Test HTML parser recognizes HTML files."""
        parser = HtmlParser()
        assert parser.supports("page.html") is True
        assert parser.supports("page.htm") is True
        assert parser.supports("page.txt") is False

    def test_eml_parser_supports(self):
        """Test EML parser recognizes EML files."""
        parser = EmlParser()
        assert parser.supports("email.eml") is True
        assert parser.supports("email.txt") is False

    def test_ocr_parser_supports(self):
        """Test OCR parser recognizes image files."""
        parser = OcrParser()
        assert parser.supports("image.png") is True
        assert parser.supports("image.jpg") is True
        assert parser.supports("image.jpeg") is True
        assert parser.supports("document.pdf") is False


# --- HTML Parser Tests ---


class TestHtmlParser:
    """Tests for HTML parser."""

    def test_parse_html_file(self):
        """Test parsing an HTML file."""
        parser = HtmlParser()

        # Create temp HTML file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False
        ) as f:
            f.write("<html><body><p>Alice is a doctor</p></body></html>")
            html_path = f.name

        try:
            triples = parser.parse(html_path)
            assert len(triples) > 0
        finally:
            Path(html_path).unlink()


# --- Pipeline Tests ---


class TestPipeline:
    """Tests for distill() pipeline."""

    def test_get_parser_html(self):
        """Test parser selection for HTML files."""
        parser = get_parser("test.html")
        assert isinstance(parser, HtmlParser)

    def test_get_parser_unknown(self):
        """Test parser selection for unknown file type."""
        parser = get_parser("test.xyz")
        assert parser is None

    def test_save_triples(self):
        """Test saving triples to JSONL."""
        triples = [
            Triple(subject="A", predicate="is", object="B"),
            Triple(subject="C", predicate="has", object="D"),
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            output_path = f.name

        try:
            count = save_triples(triples, output_path)
            assert count == 2

            # Verify file contents
            with open(output_path) as f:
                lines = f.readlines()
                assert len(lines) == 2
        finally:
            Path(output_path).unlink()
