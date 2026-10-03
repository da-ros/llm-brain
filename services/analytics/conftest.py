"""Keep this service's top-level modules from colliding with sibling services."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("ANALYTICS_STORE", "memory")
os.environ.setdefault("RAG_SERVICE_URL", "http://rag-service:8002")
os.environ.setdefault("LLM_SERVICE_URL", "http://llm-service:8003")
os.environ.setdefault("ETL_SERVICE_URL", "http://etl-service:8001")
os.environ.setdefault("LLM_TEMPERATURE", "0")

SERVICE_ROOT = Path(__file__).resolve().parent

_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "exceptions",
    "base",
    "db",
    "loaders",
    "llm_client",
    "rag_client",
    "etl_client",
    "pearson",
    "pipeline",
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


def _live_app_globals(app):
    """Module dict the imported app closed over.

    Sibling conftests drop shared top-level names from ``sys.modules``. The
    FastAPI app keeps those module objects alive; put them back so patches and
    ``reset_memory`` hit the store the routes use.
    """
    if app is None:
        return None
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        globs = getattr(endpoint, "__globals__", None)
        if not globs:
            continue
        file = str(globs.get("__file__", "")).replace("\\", "/")
        if not file.endswith("services/analytics/main.py"):
            continue
        pipe = globs.get("pipeline")
        db_mod = globs.get("db")
        if pipe is not None:
            sys.modules["pipeline"] = pipe
        if db_mod is not None:
            sys.modules["db"] = db_mod
        return globs
    return None


def _reset_analytics_db() -> None:
    db_mod = sys.modules.get("db")
    file = str(getattr(db_mod, "__file__", "") or "").replace("\\", "/")
    if db_mod is not None and file.endswith("services/analytics/db.py"):
        db_mod.reset_memory()
        return
    import db

    db.reset_memory()


@pytest.fixture(autouse=True)
def _reload_this_service(request):
    isolate_service_imports()
    globs = _live_app_globals(getattr(request.module, "app", None))
    settings_fn = (globs or {}).get("get_settings")
    wrapped = getattr(settings_fn, "__wrapped__", None)
    if wrapped is not None:
        wrapped.__globals__["clear_settings_cache"]()
    else:
        from config import clear_settings_cache

        clear_settings_cache()
    _reset_analytics_db()
    yield
    _reset_analytics_db()
