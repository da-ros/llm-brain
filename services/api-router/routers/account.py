"""Sign-up, sign-in, plan, service health, storage, and data deletion."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
from accounts import AccountExistsError, authenticate, create_account, get_account, set_plan
from auth import verify_token
from config import get_settings
from db import delete_user_uploads
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jwt import encode
from logging_setup import log_with_correlation
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/api", tags=["account"])

_SERVICE_CHECKS = (
    ("llm", "LLM core", "LLM_SERVICE_URL"),
    ("memory", "Memory retrieval", "RAG_SERVICE_URL"),
    ("personal", "Personal model", "FINETUNE_SERVICE_URL"),
    ("analytics", "Analytics", "ANALYTICS_SERVICE_URL"),
    ("agents", "Agents", "AGENTS_SERVICE_URL"),
    ("shield", "Shield", "SHIELD_SERVICE_URL"),
)


class SignupBody(BaseModel):
    name: str
    email: str
    password: str
    plan: str = "free"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Name is required")
        return cleaned[:80]

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("Enter a valid email")
        return cleaned

    @field_validator("password")
    @classmethod
    def clean_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value

    @field_validator("plan")
    @classmethod
    def clean_plan(cls, value: str) -> str:
        return _plan(value)


class SigninBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return value.strip().lower()


class PlanBody(BaseModel):
    plan: str

    @field_validator("plan")
    @classmethod
    def clean_plan(cls, value: str) -> str:
        return _plan(value)


def _plan(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in {"free", "premium"}:
        raise ValueError("Plan must be free or premium")
    return cleaned


def _token(user_id: str, plan: str) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {"sub": user_id, "subscription_tier": plan}
    if settings.JWT_EXPIRATION_MINUTES > 0:
        payload["exp"] = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    return encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _session(account: dict[str, str]) -> dict[str, Any]:
    return {
        "access_token": _token(account["id"], account["plan"]),
        "token_type": "bearer",
        "user": account,
    }


@router.post("/auth/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: Request, body: SignupBody) -> dict[str, Any]:
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "POST /api/auth/signup")
    try:
        account = await create_account(body.name, body.email, body.password, body.plan)
    except AccountExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    return _session(account)


@router.post("/auth/signin")
async def signin(request: Request, body: SigninBody) -> dict[str, Any]:
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "POST /api/auth/signin")
    account = await authenticate(body.email, body.password)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )
    return _session(account)


@router.get("/account")
async def account(
    request: Request,
    user: Annotated[dict, Depends(verify_token)],
) -> dict[str, str]:
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/account")
    found = await get_account(user["user_id"])
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return found


@router.patch("/account")
async def update_plan(
    request: Request,
    body: PlanBody,
    user: Annotated[dict, Depends(verify_token)],
) -> dict[str, Any]:
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "PATCH /api/account")
    found = await set_plan(user["user_id"], body.plan)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return _session(found)


async def _probe(client: httpx.AsyncClient, service_id: str, label: str, url: str) -> dict:
    online = False
    try:
        response = await client.get(f"{url.rstrip('/')}/health")
        online = response.status_code == 200
    except httpx.HTTPError:
        online = False
    return {"id": service_id, "label": label, "status": "online" if online else "offline"}


@router.get("/status")
async def service_status(
    request: Request,
    user: Annotated[dict, Depends(verify_token)],
) -> dict[str, Any]:
    """Health of the six product services. Personal model is the fine-tune service."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", f"GET /api/status user={user['user_id']}")
    settings = get_settings()
    async with httpx.AsyncClient(timeout=2.0) as client:
        checks = await asyncio.gather(
            *[
                _probe(client, service_id, label, getattr(settings, setting))
                for service_id, label, setting in _SERVICE_CHECKS
            ]
        )
    return {"services": checks}


@router.get("/storage")
async def storage(
    request: Request,
    user: Annotated[dict, Depends(verify_token)],
) -> dict[str, Any]:
    """Bytes occupied by the caller's raw documents in RAG."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    log_with_correlation(correlation_id, "info", "GET /api/storage")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.RAG_SERVICE_URL}/storage",
                params={"user_id": user["user_id"]},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory storage could not be loaded.",
        ) from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory storage could not be loaded.",
        )
    body = response.json()
    return {"bytes": int(body.get("bytes") or 0), "documents": int(body.get("documents") or 0)}


@router.delete("/data")
async def delete_data(
    request: Request,
    user: Annotated[dict, Depends(verify_token)],
) -> dict[str, int]:
    """Delete the caller's uploads and the RAG memory built from them."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    user_id = user["user_id"]
    log_with_correlation(correlation_id, "info", "DELETE /api/data")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{settings.RAG_SERVICE_URL}/memory",
                params={"user_id": user_id},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory could not be deleted.",
        ) from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory could not be deleted.",
        )
    body = response.json()
    uploads = await delete_user_uploads(user_id)
    return {
        "documents": int(body.get("documents") or 0),
        "embeddings": int(body.get("embeddings") or 0),
        "uploads": uploads,
    }
