"""Document Parser Protocol.

Defines the interface for all document parsers.
Each parser must implement this protocol to be used by the ETL pipeline.
"""

from typing import Protocol, runtime_checkable

from services.etl.triples import Triple


@runtime_checkable
class DocumentParser(Protocol):
    """Protocol for document parsers.

    All parsers must implement:
    - supports(): Check if parser can handle this file
    - parse(): Extract text and return triples
    """

    def supports(self, file_path: str) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file

        Returns:
            True if parser can handle this file type
        """
        ...

    def parse(self, file_path: str) -> list[Triple]:
        """Parse the file and extract triples.

        Args:
            file_path: Path to the file

        Returns:
            List of extracted triples
        """
        ...
