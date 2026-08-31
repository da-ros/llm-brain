"""EML Parser.

Extracts text from email (.eml) files using email.parser.
"""

import email
from email import policy
from pathlib import Path

from services.etl.triples import Triple, extract_triples


class EmlParser:
    """Email document parser.

    Uses email.parser for headers and body extraction.
    Handles attachments metadata.
    """

    def supports(self, file_path: str) -> bool:
        """Check if file is an EML file."""
        return file_path.lower().endswith(".eml")

    def parse(self, file_path: str) -> list[Triple]:
        """Parse email and extract triples.

        Args:
            file_path: Path to EML file

        Returns:
            List of extracted triples
        """
        path = Path(file_path)
        filename = path.name

        try:
            with open(file_path, "rb") as f:
                msg = email.message_from_binary_file(f, policy=policy.default)

            # Extract headers
            headers_text = self._extract_headers(msg)

            # Extract body
            body_text = self._extract_body(msg)

            # Combine headers and body
            full_text = f"{headers_text}\n\n{body_text}"

            if not full_text.strip():
                return []

            # Extract triples
            return extract_triples(
                text=full_text,
                source_file=filename,
            )

        except Exception as e:
            raise ValueError(f"Error parsing EML: {str(e)}")

    def _extract_headers(self, msg: email.message.Message) -> str:
        """Extract email headers as text.

        Args:
            msg: Email message object

        Returns:
            Headers as text
        """
        headers = []

        # Key headers
        key_headers = ["From", "To", "Subject", "Date"]
        for header in key_headers:
            value = msg.get(header, "")
            if value:
                headers.append(f"{header}: {value}")

        return "\n".join(headers)

    def _extract_body(self, msg: email.message.Message) -> str:
        """Extract email body text.

        Args:
            msg: Email message object

        Returns:
            Body text
        """
        body_parts = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_content()
                    if payload:
                        body_parts.append(payload)
                elif content_type == "text/html":
                    # Convert HTML to text
                    payload = part.get_content()
                    if payload:
                        body_parts.append(self._html_to_text(payload))
        else:
            payload = msg.get_content()
            if payload:
                if msg.get_content_type() == "text/html":
                    body_parts.append(self._html_to_text(payload))
                else:
                    body_parts.append(payload)

        return "\n\n".join(body_parts)

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text.

        Args:
            html: HTML content

        Returns:
            Plain text
        """
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(separator=" ", strip=True)
        except ImportError:
            # Fallback: simple tag removal
            import re

            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)
            return text.strip()
