"""Keep this service's top-level modules from colliding with sibling services."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("SIMULATOR_STORE", "memory")
os.environ.setdefault("RAG_SERVICE_URL", "http://rag-service:8002")
os.environ.setdefault("LLM_SERVICE_URL", "http://llm-service:8003")
os.environ.setdefault("LLM_TEMPERATURE", "0")

SERVICE_ROOT = Path(__file__).resolve().parent

_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "exceptions",
    "base",
    "db",
    "engine",
    "rag_client",
    "llm_client",
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


isolate_service_imports()


@pytest.fixture(autouse=True)
def _reload_this_service():
    isolate_service_imports()
    from config import clear_settings_cache

    clear_settings_cache()
    import db

    db.reset_memory()
    yield
    db.reset_memory()
