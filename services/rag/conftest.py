"""Keep this service's top-level modules from colliding with sibling services."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("EMBEDDING_MOCK", "true")
os.environ.setdefault("FERNET_KEY", "QmSFavzoGj9MohzGATx3CnkOR2I9JTP4ueRhP4P4DZ0=")
os.environ.setdefault("VECTOR_STORE_PROVIDER", "chroma")
os.environ.setdefault("CHROMA_HOST", "localhost")
os.environ.setdefault("CHROMA_PORT", "8005")

SERVICE_ROOT = Path(__file__).resolve().parent

_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "document_store",
    "vector_store",
    "embeddings",
    "rag_service",
    "conversations",
)


def isolate_service_imports(root: Path = SERVICE_ROOT) -> None:
    """Drop sibling-service modules and put this service first on sys.path."""
    root_s = str(root)
    for name in list(sys.modules):
        if name not in _TOP_LEVEL and not any(name.startswith(f"{item}.") for item in _TOP_LEVEL):
            continue
        mod = sys.modules[name]
        mod_file = getattr(mod, "__file__", None) or ""
        if mod_file and Path(mod_file).resolve().is_relative_to(root):
            continue
        del sys.modules[name]
    if root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)


def drop_this_service_imports(root: Path = SERVICE_ROOT) -> None:
    """Unload this service so later suites do not inherit its `config` module."""
    root_s = str(root)
    for name in list(sys.modules):
        if name not in _TOP_LEVEL and not any(name.startswith(f"{item}.") for item in _TOP_LEVEL):
            continue
        mod_file = getattr(sys.modules[name], "__file__", None) or ""
        if mod_file and Path(mod_file).resolve().is_relative_to(root):
            del sys.modules[name]
    if root_s in sys.path:
        sys.path.remove(root_s)


@pytest.fixture(autouse=True)
def _reload_this_service():
    isolate_service_imports()
    from config import clear_settings_cache

    clear_settings_cache()
    yield
    drop_this_service_imports()
