"""HTML Parser.

Extracts text from HTML documents using BeautifulSoup.
"""

from pathlib import Path

from services.etl.triples import Triple, extract_triples


class HtmlParser:
    """HTML document parser.

    Uses BeautifulSoup for text extraction.
    Strips tags, scripts, and styles.
    """

    def supports(self, file_path: str) -> bool:
        """Check if file is HTML."""
        return file_path.lower().endswith((".html", ".htm"))

    def parse(self, file_path: str) -> list[Triple]:
        """Parse HTML and extract triples.

        Args:
            file_path: Path to HTML file

        Returns:
            List of extracted triples
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError("BeautifulSoup is required for HTML parsing")

        path = Path(file_path)
        filename = path.name

        try:
            # Read file with encoding fallback
            content = self._read_file(file_path)

            # Parse HTML
            soup = BeautifulSoup(content, "html.parser")

            # Remove scripts and styles
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            # Get text
            text = soup.get_text(separator=" ", strip=True)

            if not text:
                return []

            # Extract triples
            return extract_triples(
                text=text,
                source_file=filename,
            )

        except Exception as e:
            raise ValueError(f"Error parsing HTML: {str(e)}")

    def _read_file(self, file_path: str) -> str:
        """Read file with encoding fallback.

        Args:
            file_path: Path to file

        Returns:
            File content as string
        """
        # Try UTF-8 first
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            pass

        # Fallback to latin-1
        try:
            with open(file_path, "r", encoding="latin-1") as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Cannot read file: {str(e)}")
