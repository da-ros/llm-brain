"""Ingestor node — persist a completed premium turn (idempotent)."""

from __future__ import annotations

from typing import Any

from logging_setup import log_with_correlation
from tools import invoke_tool


async def ingest_turn_node(state: dict[str, Any]) -> dict[str, Any]:
    """learn_graph ingest node via ingest_turn MCP tool."""
    correlation_id = state.get("correlation_id") or "no-id"
    log_with_correlation(correlation_id, "info", "learn_graph: ingest_turn")
    result = await invoke_tool(
        "ingest_turn",
        {
            "user_id": state.get("user_id") or "",
            "session_id": state.get("session_id") or "",
            "correlation_id": correlation_id,
            "query": state.get("query") or "",
            "response": state.get("response") or "",
            "assumptions": state.get("assumptions") or [],
            "sources": state.get("sources") or [],
        },
    )
    return {"error": None, "ingested": result.get("correlation_id")}
