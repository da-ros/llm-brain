"""Forward chat threads and calendar notes to the RAG service."""

from __future__ import annotations

from typing import Any

import httpx
from config import get_settings
from fastapi import HTTPException, status


def _url(path: str) -> str:
    return f"{get_settings().RAG_SERVICE_URL.rstrip('/')}{path}"


def _headers(correlation_id: str) -> dict[str, str]:
    return {"X-Request-ID": correlation_id or "no-id"}


async def _request(
    method: str,
    path: str,
    *,
    correlation_id: str,
    params: dict | None = None,
    json: dict | None = None,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.request(
                method,
                _url(path),
                params=params,
                json=json,
                headers=_headers(correlation_id),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory service is unavailable.",
        ) from exc


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    detail = "Memory service error"
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("detail"):
            detail = str(body["detail"])
    except ValueError:
        detail = response.text or detail
    status_code = (
        response.status_code if response.status_code < 500 else status.HTTP_502_BAD_GATEWAY
    )
    raise HTTPException(status_code=status_code, detail=detail)


async def list_chats(user_id: str, *, correlation_id: str = "no-id") -> list[dict[str, Any]]:
    response = await _request(
        "GET", "/chats", correlation_id=correlation_id, params={"user_id": user_id}
    )
    _raise_for_status(response)
    return list(response.json().get("chats") or [])


async def create_chat(user_id: str, *, correlation_id: str = "no-id") -> dict[str, Any]:
    response = await _request(
        "POST", "/chats", correlation_id=correlation_id, params={"user_id": user_id}
    )
    _raise_for_status(response)
    return response.json()


async def list_turns(
    user_id: str, chat_id: str, *, correlation_id: str = "no-id"
) -> list[dict[str, Any]] | None:
    response = await _request(
        "GET",
        f"/chats/{chat_id}/turns",
        correlation_id=correlation_id,
        params={"user_id": user_id},
    )
    if response.status_code == status.HTTP_404_NOT_FOUND:
        return None
    _raise_for_status(response)
    return list(response.json().get("turns") or [])


async def chat_history(
    user_id: str, chat_id: str, *, correlation_id: str = "no-id"
) -> list[dict[str, Any]] | None:
    response = await _request(
        "GET",
        f"/chats/{chat_id}/history",
        correlation_id=correlation_id,
        params={"user_id": user_id},
    )
    if response.status_code == status.HTTP_404_NOT_FOUND:
        return None
    _raise_for_status(response)
    return list(response.json().get("history") or [])


async def touch_chat(
    user_id: str, chat_id: str, message: str, *, correlation_id: str = "no-id"
) -> None:
    response = await _request(
        "POST",
        f"/chats/{chat_id}/touch",
        correlation_id=correlation_id,
        json={"user_id": user_id, "message": message},
    )
    _raise_for_status(response)


async def append_turns(
    user_id: str,
    chat_id: str,
    turns: list[dict[str, Any]],
    *,
    correlation_id: str = "no-id",
) -> None:
    response = await _request(
        "POST",
        f"/chats/{chat_id}/turns",
        correlation_id=correlation_id,
        json={"user_id": user_id, "turns": turns},
    )
    _raise_for_status(response)


async def list_notes(
    user_id: str, start: str, end: str, *, correlation_id: str = "no-id"
) -> list[dict[str, str]]:
    response = await _request(
        "GET",
        "/notes",
        correlation_id=correlation_id,
        params={"user_id": user_id, "start": start, "end": end},
    )
    _raise_for_status(response)
    return list(response.json().get("notes") or [])


async def put_note(user_id: str, day: str, note: str, *, correlation_id: str = "no-id") -> None:
    response = await _request(
        "PUT",
        f"/notes/{day}",
        correlation_id=correlation_id,
        json={"user_id": user_id, "note": note},
    )
    _raise_for_status(response)
