"""Pytest defaults so `apps.api.main:app` can import during collection."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("LLM_PROVIDER", "qwen_local")
os.environ.setdefault("LLM_SERVICE_URL", "http://localhost:8003")
os.environ.setdefault("LLM_MODEL", "Qwen3.5-4B")
