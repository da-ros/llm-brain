"""PDF Parser.

Extracts text from PDF documents using PyPDF2.
Falls back to OCR for scanned PDFs.
"""

from pathlib import Path

from services.etl.triples import Triple, extract_triples


class PdfParser:
    """PDF document parser.

    Uses PyPDF2 for text extraction.
    Falls back to OCR for scanned pages.
    """

    def supports(self, file_path: str) -> bool:
        """Check if file is a PDF."""
        return file_path.lower().endswith(".pdf")

    def parse(self, file_path: str) -> list[Triple]:
        """Parse PDF and extract triples.

        Args:
            file_path: Path to PDF file

        Returns:
            List of extracted triples
        """
        try:
            import PyPDF2
        except ImportError:
            raise ImportError("PyPDF2 is required for PDF parsing")

        triples = []
        path = Path(file_path)
        filename = path.name

        try:
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)

                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()

                    if text and text.strip():
                        # Extract triples from text
                        page_triples = extract_triples(
                            text=text,
                            source_file=filename,
                            page=page_num + 1,
                        )
                        triples.extend(page_triples)
                    else:
                        # Page might be scanned image — try OCR
                        ocr_triples = self._ocr_fallback(file_path, page_num, filename)
                        triples.extend(ocr_triples)

        except Exception as e:
            raise ValueError(f"Error parsing PDF: {str(e)}")

        return triples

    def _ocr_fallback(
        self, file_path: str, page_num: int, filename: str
    ) -> list[Triple]:
        """Fallback to OCR for scanned pages.

        Args:
            file_path: Path to PDF file
            page_num: Page number (0-indexed)
            filename: Source filename

        Returns:
            List of extracted triples
        """
        try:
            from pdf2image import convert_from_path
            import pytesseract

            # Convert page to image
            images = convert_from_path(file_path, first_page=page_num + 1, last_page=page_num + 1)

            if not images:
                return []

            # OCR the image
            text = pytesseract.image_to_string(images[0], lang="eng+spa")

            if text and text.strip():
                return extract_triples(
                    text=text,
                    source_file=filename,
                    page=page_num + 1,
                )

        except Exception:
            pass  # OCR not available or failed

        return []
