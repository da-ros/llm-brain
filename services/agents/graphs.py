"""Compiled LangGraph graphs: reason_graph (sync chat) and learn_graph (Kafka)."""

from __future__ import annotations

from typing import Any

from evaluador import evaluate_turn_node, maybe_append_batch_node
from ingestor import ingest_turn_node
from langgraph.graph import END, START, StateGraph
from logging_setup import log_with_correlation
from razonador import extract_assumptions, generate_answer, retrieve_context, route_after_generate
from state import LearnState, ReasonState


def build_reason_graph():
    """START → retrieve_context → generate_answer → extract_assumptions → END.

    LLM 5xx/timeout takes generate_answer → error END (no ingest).
    """
    builder: StateGraph = StateGraph(ReasonState)
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("extract_assumptions", extract_assumptions)
    builder.add_edge(START, "retrieve_context")
    builder.add_edge("retrieve_context", "generate_answer")
    builder.add_conditional_edges(
        "generate_answer",
        route_after_generate,
        {"assumptions": "extract_assumptions", "error": END},
    )
    builder.add_edge("extract_assumptions", END)
    return builder.compile()


def build_learn_graph():
    """START → ingest_turn → evaluate_turn → maybe_append_batch → END.

    Fine-Tune POST /train is never invoked on this graph.
    """
    builder: StateGraph = StateGraph(LearnState)
    builder.add_node("ingest_turn", ingest_turn_node)
    builder.add_node("evaluate_turn", evaluate_turn_node)
    builder.add_node("maybe_append_batch", maybe_append_batch_node)
    builder.add_edge(START, "ingest_turn")
    builder.add_edge("ingest_turn", "evaluate_turn")
    builder.add_edge("evaluate_turn", "maybe_append_batch")
    builder.add_edge("maybe_append_batch", END)
    return builder.compile()


reason_graph = build_reason_graph()
learn_graph = build_learn_graph()


async def run_reason_graph(state: dict[str, Any]) -> dict[str, Any]:
    """Facade used by POST /reason."""
    correlation_id = state.get("correlation_id") or "no-id"
    log_with_correlation(correlation_id, "info", "reason_graph.invoke")
    return await reason_graph.ainvoke(state)


async def run_learn_graph(state: dict[str, Any]) -> dict[str, Any]:
    """Facade used by the Kafka session.turn.completed consumer."""
    correlation_id = state.get("correlation_id") or "no-id"
    log_with_correlation(correlation_id, "info", "learn_graph.invoke")
    return await learn_graph.ainvoke(state)
