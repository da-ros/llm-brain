"""Keep this service's top-level modules from colliding with sibling services."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent

_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "exceptions",
    "pipeline",
    "lora",
    "providers",
    "routers",
    "kafka_io",
    "db",
    "auth",
    "rate_limit",
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
    """Sibling services share top-level names (config, main, db). Re-isolate per test."""
    isolate_service_imports()
    yield
