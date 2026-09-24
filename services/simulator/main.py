"""Simulator Service — FastAPI application on port 8007.

Clients never call this port. The API Router is the facade. Simulate is
synchronous HTTP: decision tree, one LLM call, MongoDB. No Kafka.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import db
import llm_client
import rag_client
from base import ensure_premium, owned_or_404
from config import get_settings
from engine import (
    FAMILY_KEYS,
    detect_families,
    families_covered,
    resolve_variables,
    walk_tree,
)
from exceptions import LLMTimeoutError, LLMUpstreamError, RAGTimeoutError, RAGUpstreamError
from fastapi import FastAPI, HTTPException, Request, status
from logging_setup import correlation_id_var, log_with_correlation, logger
from pydantic import BaseModel, Field


async def add_correlation_id(request: Request, call_next):
    """Propagate X-Request-ID, or mint a UUID when the inbound header is missing."""
    correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    token = correlation_id_var.set(correlation_id)
    log_with_correlation(correlation_id, "info", f"{request.method} {request.url.path}")
    try:
        response = await call_next(request)
    finally:
        correlation_id_var.reset(token)
    response.headers["X-Request-ID"] = correlation_id
    return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await db.connect()
        await db.ensure_indexes()
    except Exception:
        logger.exception("MongoDB connection failed at startup (health still 200)")
    yield
    await db.disconnect()


class SimulateRequest(BaseModel):
    user_id: str
    question: str = ""
    variables: dict[str, Any] | None = None
    subscription_tier: str | None = None


class ScenarioOut(BaseModel):
    id: str
    title: str
    outcome: str
    assumptions: list[str]
    trace: list[str]
    severity: str


class SimulateResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    simulation_id: str
    scenario_count: int
    scenarios: list[ScenarioOut]
    assumptions: list[str]
    sources: list[str] = Field(default_factory=list)
    llm_used: bool
    correlation_id: str
    model_id: str | None = None


def create_app() -> FastAPI:
    """Build the FastAPI application (used by tests and uvicorn)."""
    settings = get_settings()
    application = FastAPI(
        title="Simulator Service",
        description="Decision-support what-if simulator (port 8007)",
        version=settings.SERVICE_VERSION,
        lifespan=lifespan,
    )
    application.middleware("http")(add_correlation_id)

    @application.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
        }

    @application.post("/simulate", response_model=SimulateResponse)
    async def simulate(request: Request, body: SimulateRequest):
        correlation_id = request.state.correlation_id
        tier = (
            body.subscription_tier
            or request.headers.get("X-Subscription-Tier")
            or "free"
        )
        log_with_correlation(
            correlation_id,
            "info",
            f"POST /simulate user_id={body.user_id} tier={tier}",
        )
        ensure_premium(tier)
        question = (body.question or "").strip()
        if not question:
            log_with_correlation(correlation_id, "warning", "POST /simulate blank question")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="question is required",
            )

        existing = await db.find_by_correlation(correlation_id)
        if existing is not None:
            if existing.get("user_id") != body.user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
            log_with_correlation(
                correlation_id,
                "info",
                "correlation_id hit — returning stored simulation",
            )
            return _to_response(existing)

        families = detect_families(question, body.variables)
        excerpts = ""
        sources: list[str] = []
        parsed: dict[str, float] = {}
        if families_covered(families, body.variables):
            log_with_correlation(
                correlation_id,
                "info",
                "RAG hydrate skipped — client variables cover detected families",
            )
        else:
            try:
                hydration = await rag_client.hydrate(
                    question=question,
                    user_id=body.user_id,
                    correlation_id=correlation_id,
                )
            except RAGTimeoutError as exc:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="RAG service timeout",
                ) from exc
            except RAGUpstreamError as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="RAG service error",
                ) from exc
            excerpts = hydration.excerpts
            sources = hydration.sources if hydration.hit_count else []
            parsed = hydration.parsed

        try:
            variables, default_notes = resolve_variables(
                families,
                body.variables,
                parsed,
                settings,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        leaves = walk_tree(families, variables)
        log_with_correlation(
            correlation_id,
            "info",
            f"decision tree leaves={[leaf['id'] for leaf in leaves]} count={len(leaves)}",
        )
        try:
            authored = await llm_client.reason_scenarios(
                question=question,
                variables=variables,
                excerpts=excerpts,
                leaves=leaves,
                user_id=body.user_id,
                correlation_id=correlation_id,
            )
        except LLMTimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="LLM service timeout",
            ) from exc
        except LLMUpstreamError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM service error",
            ) from exc

        scenarios = _merge_scenarios(leaves, authored, default_notes)
        assumptions = _flatten_assumptions(scenarios)
        document = {
            "user_id": body.user_id,
            "correlation_id": correlation_id,
            "question": question,
            "variables": variables,
            "sources": sources,
            "scenarios": scenarios,
            "assumptions": assumptions,
            "scenario_count": len(scenarios),
            "llm_used": True,
            "model_id": settings.LLM_MODEL_ID,
        }
        stored = await db.insert_simulation(document)
        log_with_correlation(
            correlation_id,
            "info",
            f"persisted simulation id={stored['_id']} correlation_id={correlation_id}",
        )
        return _to_response(stored)

    @application.get("/simulations")
    async def list_simulations(
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        tier = subscription_tier or request.headers.get("X-Subscription-Tier") or "free"
        log_with_correlation(correlation_id, "info", f"GET /simulations user_id={user_id}")
        ensure_premium(tier)
        rows = await db.list_for_user(user_id)
        return {"simulations": [_to_response(row).model_dump() for row in rows]}

    @application.get("/simulations/{simulation_id}")
    async def get_simulation(
        simulation_id: str,
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        tier = subscription_tier or request.headers.get("X-Subscription-Tier") or "free"
        log_with_correlation(
            correlation_id,
            "info",
            f"GET /simulations/{simulation_id} user_id={user_id}",
        )
        ensure_premium(tier)
        document = owned_or_404(await db.find_by_id(simulation_id), user_id)
        return _to_response(document)

    logger.info("Simulator Service ready — port=%s", settings.SIMULATOR_PORT)
    return application


def _merge_scenarios(
    leaves: list[dict[str, Any]],
    authored: list[dict[str, Any]],
    default_notes: dict[str, str],
) -> list[dict[str, Any]]:
    by_id = {row["id"]: row for row in authored}
    scenarios: list[dict[str, Any]] = []
    for leaf in leaves:
        row = by_id[leaf["id"]]
        assumptions = list(row["assumptions"])
        for key in FAMILY_KEYS[leaf["family"]]:
            note = default_notes.get(key)
            if note and note not in assumptions:
                assumptions.append(note)
        scenarios.append(
            {
                "id": leaf["id"],
                "title": row["title"],
                "outcome": row["outcome"],
                "assumptions": assumptions,
                "trace": list(leaf["trace"]),
                "severity": leaf["severity"],
            }
        )
    return scenarios


def _flatten_assumptions(scenarios: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for scenario in scenarios:
        for item in scenario["assumptions"]:
            if item not in seen:
                seen.append(item)
    return seen


def _to_response(document: dict[str, Any]) -> SimulateResponse:
    scenarios = document.get("scenarios") or []
    return SimulateResponse(
        simulation_id=str(document.get("_id") or document.get("simulation_id")),
        scenario_count=int(document.get("scenario_count") or len(scenarios)),
        scenarios=scenarios,
        assumptions=document.get("assumptions") or _flatten_assumptions(scenarios),
        sources=document.get("sources") or [],
        llm_used=bool(document.get("llm_used")),
        correlation_id=document.get("correlation_id") or "",
        model_id=document.get("model_id"),
    )


app = create_app()
