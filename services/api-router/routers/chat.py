"""Chat router — premium via Agents Razonador; free skips agents and Kafka.

CHAT_VIA_AGENTS=false restores the previous Router → RAG → LLM path (rollback).

An attachment is not written to documents, GridFS, or RAG.
Its text stays on the chat and is sent again with later questions in that chat.
"""

import base64
from datetime import date, timedelta
from typing import Annotated, Literal

import httpx
from attachment_loader import (
    EmptyAttachmentError,
    UnsupportedAttachmentError,
    load_attachment,
    supported_summary,
)
from auth import verify_token
from brain_client import append_turns, chat_history, list_notes, touch_chat
from config import get_settings
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from kafka_io import publish_session_turn_completed
from logging_setup import log_with_correlation
from pydantic import BaseModel, Field
from rate_limit import rate_limit_chat

router = APIRouter(prefix="/api", tags=["chat"])

EMPTY_CONTEXT = "No relevant context found in your documents."
MAX_ATTACHMENT_BYTES = 8_000_000
MAX_CHAT_FILES = 5


class ChatAttachment(BaseModel):
    """One file read for this question only. It is not stored."""

    filename: str = "attachment"
    content_base64: str = ""


class ChatRequest(BaseModel):
    """Chat request schema."""

    message: str
    use_rag: bool = True
    session_id: str | None = None
    attachment_filename: str | None = None
    attachment_base64: str | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list)


class SourceCard(BaseModel):
    n: int
    label: str
    origin: Literal["memory", "calendar", "attachment"]


class ChatResponse(BaseModel):
    """Chat response schema."""

    response: str
    context_used: bool
    sources: list[str] = []
    source_cards: list[SourceCard] = []
    assumptions: list[str] = []
    tokens_used: int = 0
    session_id: str | None = None
    correlation_id: str


async def _rag_context(
    *,
    message: str,
    user_id: str,
    correlation_id: str,
    rag_url: str,
) -> tuple[str, list[str]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{rag_url}/context",
            params={"query": message, "user_id": user_id},
            headers={"X-Request-ID": correlation_id},
        )
    if response.status_code != 200:
        return "", []
    data = response.json()
    return data.get("context") or "", data.get("sources") or []


async def _llm_generate(
    *,
    prompt: str,
    user_id: str,
    tier: str,
    correlation_id: str,
    llm_url: str,
) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{llm_url}/generate",
            json={"prompt": prompt, "user_id": user_id, "tier": tier},
            headers={"X-Request-ID": correlation_id},
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM service error",
        )
    return response.json().get("response") or ""


async def _agents_reason(
    *,
    message: str,
    user_id: str,
    session_id: str | None,
    correlation_id: str,
    agents_url: str,
) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{agents_url}/reason",
            json={
                "user_id": user_id,
                "subscription_tier": "premium",
                "message": message,
                "session_id": session_id,
            },
            headers={"X-Request-ID": correlation_id},
        )
    if response.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM service timeout",
        )
    if response.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agents service error",
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Agents service error")
    return response.json()


def _publish_turn(payload: dict) -> None:
    try:
        publish_session_turn_completed(payload)
    except Exception as exc:
        log_with_correlation(
            payload.get("correlation_id", "no-id"),
            "warning",
            f"Kafka session.turn.completed skipped: {exc}",
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[dict, Depends(verify_token)],
    _: Annotated[dict, Depends(rate_limit_chat)],
):
    """Premium chat uses Razonador. Free chat skips agents, RAG, and Kafka."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    user_id = user["user_id"]
    tier = user.get("subscription_tier", "free")

    log_with_correlation(correlation_id, "info", "POST /api/chat")
    log_with_correlation(
        correlation_id,
        "info",
        f"JWT validated: user_id={user_id}, tier={tier}",
    )

    attachments = _read_attachments(chat_request)
    history = await _history(user_id, chat_request.session_id, correlation_id)
    notes = await _prompt_notes(user_id, correlation_id) if tier == "premium" else []
    use_agents = (
        tier == "premium"
        and settings.CHAT_VIA_AGENTS
        and not attachments
        and not notes
    )

    if use_agents:
        log_with_correlation(correlation_id, "info", "Calling Agents Service POST /reason")
        try:
            data = await _agents_reason(
                message=_with_history(history, chat_request.message),
                user_id=user_id,
                session_id=chat_request.session_id,
                correlation_id=correlation_id,
                agents_url=settings.AGENTS_SERVICE_URL,
            )
        except httpx.TimeoutException as exc:
            log_with_correlation(correlation_id, "error", "Agents service timeout")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Agents service timeout",
            ) from exc
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            log_with_correlation(correlation_id, "error", f"Error calling Agents service: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error calling Agents service: {exc}",
            ) from exc

        response_text = data.get("response") or ""
        sources = data.get("sources") or []
        assumptions = data.get("assumptions") or []
        session_id = data.get("session_id") or chat_request.session_id
        tokens_used = int(data.get("tokens_used") or 0)
        background_tasks.add_task(
            _publish_turn,
            {
                "correlation_id": correlation_id,
                "user_id": user_id,
                "session_id": session_id,
                "query": chat_request.message,
                "response": response_text,
                "assumptions": assumptions,
                "sources": sources,
            },
        )
        await _name_chat(user_id, session_id, chat_request.message, correlation_id)
        cards = _source_cards(sources, None, [])
        await _remember(
            user_id,
            session_id,
            chat_request.message,
            response_text,
            cards,
            assumptions,
            [],
            correlation_id,
        )
        log_with_correlation(correlation_id, "info", "Response: 200 OK (Razonador)")
        return ChatResponse(
            response=response_text,
            context_used=bool(sources),
            sources=sources,
            source_cards=cards,
            assumptions=assumptions,
            tokens_used=tokens_used,
            session_id=session_id,
            correlation_id=correlation_id,
        )

    context = ""
    sources: list[str] = []
    context_used = False

    if chat_request.use_rag and tier == "premium":
        log_with_correlation(correlation_id, "info", "Calling RAG Service for context")
        try:
            context, sources = await _rag_context(
                message=chat_request.message,
                user_id=user_id,
                correlation_id=correlation_id,
                rag_url=settings.RAG_SERVICE_URL,
            )
            if context and context != EMPTY_CONTEXT:
                context_used = True
                log_with_correlation(
                    correlation_id,
                    "info",
                    f"RAG context received: {len(sources)} sources",
                )
        except httpx.HTTPError as exc:
            log_with_correlation(
                correlation_id,
                "warning",
                f"RAG service unavailable, continuing without context: {exc}",
            )

    prompt = _prompt(
        chat_request.message,
        context=context,
        context_used=context_used,
        notes=notes,
        attachments=attachments,
        history=history,
    )

    log_with_correlation(correlation_id, "info", "Calling LLM Service for response")
    try:
        response_text = await _llm_generate(
            prompt=prompt,
            user_id=user_id,
            tier=tier,
            correlation_id=correlation_id,
            llm_url=settings.LLM_SERVICE_URL,
        )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "LLM service timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM service timeout",
        ) from exc
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Error calling LLM service: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error calling LLM service: {exc}",
        ) from exc

    calendar_label = _calendar_label(notes)
    cards = _source_cards(sources, calendar_label, [name for name, _text in attachments])
    if tier == "premium" and settings.CHAT_VIA_AGENTS:
        background_tasks.add_task(
            _publish_turn,
            {
                "correlation_id": correlation_id,
                "user_id": user_id,
                "session_id": chat_request.session_id,
                "query": chat_request.message,
                "response": response_text,
                "assumptions": [],
                "sources": sources,
            },
        )
    await _name_chat(user_id, chat_request.session_id, chat_request.message, correlation_id)
    await _remember(
        user_id,
        chat_request.session_id,
        chat_request.message,
        response_text,
        cards,
        [],
        attachments,
        correlation_id,
    )
    log_with_correlation(correlation_id, "info", "LLM response received")
    log_with_correlation(correlation_id, "info", "Response: 200 OK")

    return ChatResponse(
        response=response_text,
        context_used=context_used,
        sources=sources,
        source_cards=cards,
        assumptions=[],
        tokens_used=0,
        session_id=chat_request.session_id,
        correlation_id=correlation_id,
    )


def _read_attachments(chat_request: ChatRequest) -> list[tuple[str, str]]:
    items = list(chat_request.attachments)
    if chat_request.attachment_base64:
        items.append(
            ChatAttachment(
                filename=chat_request.attachment_filename or "attachment",
                content_base64=chat_request.attachment_base64,
            )
        )
    if len(items) > MAX_CHAT_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You can attach up to five files for one question.",
        )
    return [_decode_attachment(item.filename, item.content_base64) for item in items]


def _decode_attachment(filename: str, content_base64: str) -> tuple[str, str]:
    name = (filename or "attachment").strip() or "attachment"
    try:
        data = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Attachment is not valid base64",
        ) from exc
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Attachment is empty or larger than 8 MB",
        )
    try:
        return name, load_attachment(name, data)
    except UnsupportedAttachmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file. {supported_summary()}",
        ) from exc
    except EmptyAttachmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Attachment is empty",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not read that file",
        ) from exc


async def _history(user_id: str, session_id: str | None, correlation_id: str) -> list[dict]:
    if not session_id:
        return []
    rows = await chat_history(user_id, session_id, correlation_id=correlation_id)
    return rows or []


def _history_text(history: list[dict]) -> str:
    if not history:
        return ""
    parts: list[str] = []
    for turn in history:
        speaker = "User" if turn.get("role") == "user" else "Encefalus"
        parts.append(f"{speaker}: {turn.get('text') or ''}")
        for item in turn.get("files") or []:
            name = (item.get("name") or "attachment").strip() or "attachment"
            body = (item.get("text") or "").strip() or "No text could be extracted."
            parts.append(f"Attached file {name} (not saved to memory):\n{body}")
    return "Earlier in this chat:\n\n" + "\n\n".join(parts)


def _with_history(history: list[dict], message: str) -> str:
    earlier = _history_text(history)
    if not earlier:
        return message
    return f"{earlier}\n\nAnswer the user's question: {message}"


async def _prompt_notes(user_id: str, correlation_id: str) -> list[dict[str, str]]:
    today = date.today()
    start = (today - timedelta(days=7)).isoformat()
    end = (today + timedelta(days=14)).isoformat()
    return await list_notes(user_id, start, end, correlation_id=correlation_id)


def _prompt(
    message: str,
    *,
    context: str,
    context_used: bool,
    notes: list[dict[str, str]],
    attachments: list[tuple[str, str]],
    history: list[dict],
) -> str:
    blocks: list[str] = []
    earlier = _history_text(history)
    if earlier:
        blocks.append(earlier)
    if context_used:
        blocks.append(f"Context from the user's documents:\n\n{context}")
    if notes:
        lines = "\n".join(f"- {note['date']}: {note['note']}" for note in notes)
        blocks.append(f"Calendar notes (not documents):\n{lines}")
    for attachment_name, attachment_text in attachments:
        body = attachment_text.strip() or "No text could be extracted."
        blocks.append(f"Attached file {attachment_name} (not saved to memory):\n{body}")
    if not blocks:
        return message
    return "\n\n".join(blocks) + f"\n\nAnswer the user's question: {message}"


def _calendar_label(notes: list[dict[str, str]]) -> str | None:
    if not notes:
        return None
    dates = sorted(note["date"] for note in notes)
    start = date.fromisoformat(dates[0])
    end = date.fromisoformat(dates[-1])
    if start == end:
        return f"{start.strftime('%b')} {start.day}"
    if start.month == end.month and start.year == end.year:
        return f"{start.strftime('%b')} {start.day}-{end.day}"
    return f"{start.strftime('%b')} {start.day}-{end.strftime('%b')} {end.day}"


def _source_cards(
    sources: list[str],
    calendar_label: str | None,
    attachment_names: list[str],
) -> list[SourceCard]:
    cards: list[tuple[str, Literal["memory", "calendar", "attachment"]]] = [
        (label, "memory") for label in (str(item).strip() for item in sources) if label
    ]
    if calendar_label:
        cards.append((calendar_label, "calendar"))
    cards.extend((name, "attachment") for name in attachment_names if name)
    return [
        SourceCard(n=index + 1, label=label, origin=origin)
        for index, (label, origin) in enumerate(cards)
    ]


async def _name_chat(
    user_id: str, session_id: str | None, message: str, correlation_id: str
) -> None:
    if session_id:
        await touch_chat(user_id, session_id, message, correlation_id=correlation_id)


async def _remember(
    user_id: str,
    session_id: str | None,
    message: str,
    response_text: str,
    cards: list[SourceCard],
    assumptions: list[str],
    attachments: list[tuple[str, str]],
    correlation_id: str,
) -> None:
    if not session_id:
        return
    await append_turns(
        user_id,
        session_id,
        [
            {
                "role": "user",
                "text": message,
                "cards": [],
                "assumptions": [],
                "files": [{"name": name, "text": text} for name, text in attachments],
            },
            {
                "role": "assistant",
                "text": response_text,
                "cards": [card.model_dump() for card in cards],
                "assumptions": assumptions,
            },
        ],
        correlation_id=correlation_id,
    )
