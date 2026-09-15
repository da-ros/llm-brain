"""Keep this service's top-level modules from colliding with sibling services."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("KAFKA_ENABLED", "false")
os.environ.setdefault("LLM_SERVICE_URL", "http://localhost:8003")

SERVICE_ROOT = Path(__file__).resolve().parent

_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "exceptions",
    "pipeline",
    "base",
    "loaders",
    "triples",
    "llm_client",
    "jsonl",
    "kafka_io",
    "gridfs_store",
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
    """Sibling services share top-level names (config, main). Re-isolate per test."""
    isolate_service_imports()
    yield
    drop_this_service_imports()
