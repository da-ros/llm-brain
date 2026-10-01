"""Agents Service — FastAPI application on port 8006.

LangGraph orchestrates Ingestor / Razonador / Evaluador. Clients never call
this port; the API Router is the facade.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import db
import kafka_io
from base import ensure_premium, owned_or_404
from config import get_settings
from evaluador import finalize_session, trigger_batch
from exceptions import LLMTimeoutError, LLMUpstreamError, UnknownToolError
from fastapi import FastAPI, HTTPException, Request, status
from graphs import run_reason_graph
from learning import build_learning
from logging_setup import correlation_id_var, log_with_correlation, logger
from pydantic import BaseModel, Field
from tools import invoke_tool, list_tools


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
    settings = get_settings()
    try:
        await db.connect()
        await db.ensure_indexes()
    except Exception:
        logger.exception("MongoDB connection failed at startup (health still 200)")
    if settings.KAFKA_ENABLED:
        kafka_io.start_consumer_thread()
    else:
        logger.info("Kafka consumer disabled (KAFKA_ENABLED=false)")
    yield
    kafka_io.stop_consumer_thread()
    await db.disconnect()


class ReasonRequest(BaseModel):
    user_id: str
    subscription_tier: str = "free"
    message: str
    session_id: str | None = None


class ReasonResponse(BaseModel):
    response: str
    assumptions: list[str]
    sources: list[str] = Field(default_factory=list)
    tokens_used: int = 0
    session_id: str
    correlation_id: str


class TriggerRequest(BaseModel):
    user_id: str
    subscription_tier: str = "premium"


class SessionEndRequest(BaseModel):
    user_id: str
    session_id: str
    subscription_tier: str = "premium"


def create_app() -> FastAPI:
    """Build the FastAPI application (used by tests and uvicorn)."""
    settings = get_settings()
    application = FastAPI(
        title="Agents Service",
        description="Symbiotic learning loop — LangGraph + MCP tools (port 8006)",
        version=settings.SERVICE_VERSION,
        lifespan=lifespan,
    )
    application.middleware("http")(add_correlation_id)

    @application.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "service": settings.SERVICE_NAME,
            "orchestrator": settings.ORCHESTRATOR,
            "version": settings.SERVICE_VERSION,
        }

    @application.get("/mcp/tools")
    async def mcp_list_tools():
        return {"tools": list_tools()}

    @application.post("/mcp/tools/{name}")
    async def mcp_invoke_tool(name: str, request: Request, body: dict[str, Any] | None = None):
        arguments = dict(body or {})
        arguments.setdefault("correlation_id", request.state.correlation_id)
        if "subscription_tier" in arguments:
            ensure_premium(arguments.get("subscription_tier"))
        try:
            return await invoke_tool(name, arguments)
        except UnknownToolError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown tool: {exc.name}",
            ) from exc
        except LLMTimeoutError as exc:
            log_with_correlation(request.state.correlation_id, "error", str(exc))
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Upstream service timeout",
            ) from exc
        except LLMUpstreamError as exc:
            log_with_correlation(request.state.correlation_id, "error", str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Upstream service error",
            ) from exc

    @application.post("/reason", response_model=ReasonResponse)
    async def reason(request: Request, body: ReasonRequest):
        ensure_premium(body.subscription_tier)
        correlation_id = request.state.correlation_id
        session_id = body.session_id or str(uuid.uuid4())
        log_with_correlation(
            correlation_id,
            "info",
            f"POST /reason user_id={body.user_id} session_id={session_id}",
        )
        result = await run_reason_graph(
            {
                "user_id": body.user_id,
                "session_id": session_id,
                "correlation_id": correlation_id,
                "query": body.message,
                "context": "",
                "sources": [],
                "response": "",
                "assumptions": [],
                "tokens_used": 0,
                "error": None,
                "error_kind": None,
            }
        )
        if result.get("error"):
            kind = result.get("error_kind")
            log_with_correlation(
                correlation_id,
                "error",
                f"reason_graph error ({kind}): {result.get('error')}",
            )
            if kind == "timeout":
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="LLM service timeout",
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM service error",
            )
        return ReasonResponse(
            response=result.get("response") or "",
            assumptions=result.get("assumptions") or [],
            sources=result.get("sources") or [],
            tokens_used=int(result.get("tokens_used") or 0),
            session_id=session_id,
            correlation_id=correlation_id,
        )

    @application.post("/batches/{batch_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
    async def trigger(batch_id: str, request: Request, body: TriggerRequest):
        ensure_premium(body.subscription_tier)
        return await trigger_batch(
            batch_id=batch_id,
            user_id=body.user_id,
            correlation_id=request.state.correlation_id,
        )

    @application.get("/batches/{batch_id}")
    async def get_batch(batch_id: str, user_id: str):
        return owned_or_404(await db.find_batch(batch_id), user_id)

    @application.get("/batches")
    async def get_batches(user_id: str):
        return {"batches": await db.list_batches(user_id)}

    @application.get("/learning")
    async def learning(request: Request, user_id: str):
        log_with_correlation(request.state.correlation_id, "info", f"GET /learning user_id={user_id}")
        return await build_learning(user_id, request.state.correlation_id)

    @application.get("/interactions/{correlation_id}")
    async def get_interaction(correlation_id: str, user_id: str):
        return owned_or_404(await db.find_interaction(correlation_id), user_id)

    @application.post("/sessions/end", status_code=status.HTTP_202_ACCEPTED)
    async def session_end(request: Request, body: SessionEndRequest):
        ensure_premium(body.subscription_tier)
        return await finalize_session(
            user_id=body.user_id,
            session_id=body.session_id,
            correlation_id=request.state.correlation_id,
        )

    logger.info(
        "Agents Service ready — port=%s orchestrator=%s",
        settings.AGENTS_PORT,
        settings.ORCHESTRATOR,
    )
    return application


app = create_app()
