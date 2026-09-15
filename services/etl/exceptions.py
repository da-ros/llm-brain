"""Domain errors for the ETL memory-distillation pipeline."""


class ETLError(Exception):
    """Base ETL failure."""


class UnsupportedFileTypeError(ETLError):
    """MIME type is not mapped to a LangChain loader."""


class CorruptFileError(ETLError):
    """File exists but cannot be loaded as a document."""


class LoaderError(ETLError):
    """A LangChain loader failed while reading the file."""


class LLMExtractionError(ETLError):
    """LLM Service triple extraction failed."""


class FileTooLargeError(ETLError):
    """Binary exceeds the 10MB MVP limit."""
