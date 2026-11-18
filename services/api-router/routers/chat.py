"""Chat router — premium via Agents Razonador; free skips agents and Kafka.

CHAT_VIA_AGENTS=false restores the previous Router → RAG → LLM path (rollback).

An attachment is not written to documents, GridFS, or RAG.
Its text stays on the chat and is sent again with later questions in that chat.
Parsing is delegated to the ETL service (POST /parse); the router stays a gateway.
"""

import base64
import contextlib
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, NamedTuple
from zoneinfo import ZoneInfo

import httpx
from auth import verify_token
from brain_client import append_turns, chat_history, list_notes, touch_chat
from config import get_settings
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from kafka_io import publish_session_turn_completed
from logging_setup import log_with_correlation
from pydantic import BaseModel, Field
from rate_limit import rate_limit_chat


class ChatFile(NamedTuple):
    """One attachment after ETL. visual is set when the model must see the bytes."""

    name: str
    text: str
    visual: str | None
    data: bytes


_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".mpeg", ".mpg"}

router = APIRouter(prefix="/api", tags=["chat"])

EMPTY_CONTEXT = "No relevant context found in your documents."
MAX_ATTACHMENT_BYTES = 8_000_000
MAX_CHAT_FILES = 5
ETL_PARSE_TIMEOUT = 30.0


class ChatAttachment(BaseModel):
    """One file read for this question only. It is not stored."""

    filename: str = "attachment"
    content_base64: str = ""


class ChatRequest(BaseModel):
    """Chat request schema."""

    message: str
    use_rag: bool = True
    session_id: str | None = None
    memory_id: str = ""
    memory_name: str = ""
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
    media: list[dict[str, str]] | None = None,
) -> str:
    payload: dict = {"prompt": prompt, "user_id": user_id, "tier": tier}
    if media:
        payload["media"] = media
    async with httpx.AsyncClient(timeout=get_settings().INFERENCE_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{llm_url}/generate",
            json=payload,
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
    search_query: str = "",
) -> dict:
    async with httpx.AsyncClient(timeout=get_settings().INFERENCE_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{agents_url}/reason",
            json={
                "user_id": user_id,
                "subscription_tier": "premium",
                "message": message,
                "search_query": search_query,
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

    attachments = await _read_attachments(
        chat_request, correlation_id=correlation_id, etl_url=settings.ETL_SERVICE_URL
    )
    history = await _history(user_id, chat_request.session_id, correlation_id)
    # Premium sends a photo or clip only on the turn that includes it, so the
    # next question can go back through the agents with the written conversation.
    prior_media = [] if tier == "premium" else _history_media(history)
    notes = []
    if tier == "premium" and _question_uses_calendar(chat_request.message, history):
        notes = await _prompt_notes(user_id, correlation_id)
    use_agents = tier == "premium" and settings.CHAT_VIA_AGENTS and not attachments and not notes

    if use_agents:
        log_with_correlation(correlation_id, "info", "Calling Agents Service POST /reason")
        try:
            data = await _agents_reason(
                message=_agents_message(history, chat_request.message, chat_request.memory_name),
                search_query=_standalone_search(
                    history, chat_request.message, chat_request.memory_name
                ),
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
                message=_standalone_search(history, chat_request.message, chat_request.memory_name),
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
        replay_visual=bool(prior_media),
        memory_name=chat_request.memory_name,
    )

    log_with_correlation(correlation_id, "info", "Calling LLM Service for response")
    try:
        response_text = await _llm_generate(
            prompt=prompt,
            user_id=user_id,
            tier=tier,
            correlation_id=correlation_id,
            llm_url=settings.LLM_SERVICE_URL,
            media=_media(attachments, prior_media),
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
    cards = _source_cards(sources, calendar_label, [item.name for item in attachments])
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


def _visual_kind(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    return "image"


def _history_media(history: list[dict]) -> list[dict[str, str]]:
    """Earlier photos and clips in this chat, so the next turn can show them again."""
    parts: list[dict[str, str]] = []
    for turn in history:
        for item in turn.get("files") or []:
            raw = item.get("content_base64") or ""
            kind = item.get("kind")
            if raw and kind in {"image", "video"}:
                parts.append(
                    {
                        "kind": kind,
                        "filename": item.get("name") or "",
                        "content_base64": raw,
                    }
                )
    return parts


def _media(
    attachments: list[ChatFile], prior: list[dict[str, str]] | None = None
) -> list[dict[str, str]] | None:
    parts = list(prior or [])
    parts.extend(
        {
            "kind": item.visual or "",
            "filename": item.name,
            "content_base64": base64.b64encode(item.data).decode("ascii"),
        }
        for item in attachments
        if item.visual and item.data
    )
    return parts or None


async def _read_attachments(
    chat_request: ChatRequest, *, correlation_id: str, etl_url: str
) -> list[ChatFile]:
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
    parsed: list[ChatFile] = []
    for item in items:
        parsed.append(
            await _decode_attachment(
                item.filename,
                item.content_base64,
                correlation_id=correlation_id,
                etl_url=etl_url,
            )
        )
    return parsed


async def _decode_attachment(
    filename: str, content_base64: str, *, correlation_id: str, etl_url: str
) -> ChatFile:
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
    parsed = await _parse_via_etl(name, data, correlation_id=correlation_id, etl_url=etl_url)
    if isinstance(parsed, str):
        text, show_bytes = parsed, False
    else:
        text, show_bytes = parsed
    visual = _visual_kind(name) if show_bytes else None
    return ChatFile(name, text, visual, data if visual else b"")


async def _parse_via_etl(
    filename: str, data: bytes, *, correlation_id: str, etl_url: str
) -> tuple[str, bool]:
    """Parse one attachment through the ETL service (POST /parse).

    The router stays a gateway: text in, text out. Nothing is stored here.
    """
    try:
        async with httpx.AsyncClient(timeout=ETL_PARSE_TIMEOUT) as client:
            response = await client.post(
                f"{etl_url}/parse",
                content=data,
                params={"filename": filename},
                headers={
                    "X-Request-ID": correlation_id,
                    "Content-Type": "application/octet-stream",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Attachment parsing is unavailable (ETL service). "
                "Try again later or send the question without the file."
            ),
        ) from exc
    if response.status_code != 200:
        detail = "Could not read that file"
        with contextlib.suppress(ValueError):
            detail = response.json().get("detail") or detail
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    body = response.json()
    return body.get("text") or "", bool(body.get("show_bytes"))


async def _history(user_id: str, session_id: str | None, correlation_id: str) -> list[dict]:
    if not session_id:
        return []
    rows = await chat_history(user_id, session_id, correlation_id=correlation_id)
    return rows or []


def _history_text(history: list[dict], *, replay_visual: bool = False) -> str:
    if not history:
        return ""
    parts: list[str] = []
    for turn in history:
        speaker = "User" if turn.get("role") == "user" else "Encefalus"
        parts.append(f"{speaker}: {turn.get('text') or ''}")
        for item in turn.get("files") or []:
            name = (item.get("name") or "attachment").strip() or "attachment"
            kind = item.get("kind")
            if replay_visual and item.get("content_base64") and kind in {"image", "video"}:
                parts.append(
                    f"Attached {kind} {name} is included for you to see. It is not saved to memory."
                )
                continue
            body = (item.get("text") or "").strip() or "No text could be extracted."
            parts.append(f"Attached file {name} (not saved to memory):\n{body}")
    return "Earlier in this chat:\n\n" + "\n\n".join(parts)


def _with_history(history: list[dict], message: str) -> str:
    earlier = _history_text(history)
    if not earlier:
        return message
    return f"{earlier}\n\nAnswer the user's question: {message}"


def _memory_name(name: str) -> str:
    return " ".join((name or "").split())[:200]


def _memory_line(name: str) -> str:
    cleaned = _memory_name(name)
    if not cleaned:
        return ""
    return f"The user is asking about the memory file {cleaned}. Prefer facts from that file."


def _search_text(message: str, memory_name: str) -> str:
    cleaned = _memory_name(memory_name)
    text = message or ""
    if not cleaned:
        return text
    return f"{cleaned}\n{text}"


_FOLLOWUP_OPENING_RE = re.compile(
    r"^(?:yeah|yes|yep|ok|okay|and|but|so|also|right|wait|no|what about|how about)\b",
    re.I,
)
_FOLLOWUP_ANAPHOR_RE = re.compile(
    r"\b(?:its|it's|their|theirs|that|this|those|these|they|them|he|she|her|him|his)\b",
    re.I,
)
_BARE_IT_RE = re.compile(r"\bit\b", re.I)
_CORRECTION_RE = re.compile(
    r"^(?:reconsider|try again|again|wrong|nope|incorrect|that(?:'|’)s wrong)[.!?\s]*$",
    re.I,
)


def _previous_user_question(history: list[dict]) -> str:
    """The last question the user asked. Assistant replies stay out of search."""
    for turn in reversed(history or []):
        if turn.get("role") == "user":
            return " ".join(str(turn.get("text") or "").split())
    return ""


def _depends_on_prior_turn(message: str) -> bool:
    """A follow-up points at the turn before. A question that names its subject does not."""
    text = " ".join((message or "").split())
    if not text:
        return False
    if _FOLLOWUP_OPENING_RE.search(text) or _FOLLOWUP_ANAPHOR_RE.search(text):
        return True
    if _CORRECTION_RE.search(text):
        return True
    return bool(_BARE_IT_RE.search(text) and len(text.split()) <= 8)


def _standalone_search(history: list[dict], message: str, memory_name: str = "") -> str:
    """Search text for this turn. A follow-up keeps the previous question and drops the reply."""
    current = " ".join((message or "").split())
    prior = _previous_user_question(history)
    body = current
    if prior and current and _depends_on_prior_turn(current):
        body = f"{prior}\n{current}"
    return _search_text(body, memory_name)


def _agents_message(history: list[dict], message: str, memory_name: str = "") -> str:
    parts = [_clock_line()]
    focus = _memory_line(memory_name)
    if focus:
        parts.append(focus)
    aside = _off_calendar_line(history)
    if aside:
        parts.append(aside)
    parts.append(_with_history(history, message))
    if _asks_for_the_date(message):
        parts.append(_date_authority_line())
    return "\n\n".join(parts)


def _now(now: datetime | None = None) -> datetime:
    zone = ZoneInfo(get_settings().APP_TIMEZONE)
    return now.astimezone(zone) if now is not None else datetime.now(zone)


def _written_day(current: datetime) -> str:
    return f"{current.strftime('%A, %B')} {current.day}, {current.year}"


def _clock_line(now: datetime | None = None) -> str:
    """Wall clock for this request. Note dates are not a substitute for it."""
    current = _now(now)
    return (
        f"Current time: {_written_day(current)} "
        f"({current.isoformat(timespec='minutes')}, unix {int(current.timestamp())}). "
        "Answer questions about today's date from this clock."
    )


def _date_authority_line(now: datetime | None = None) -> str:
    """A date question must use the clock, including when history names another day."""
    current = _now(now)
    written = _written_day(current)
    return (
        f"The user is asking what day it is. Today's date is {written}. "
        "Answer with that date. Do not copy a date from earlier messages or calendar notes."
    )


_SCHEDULE_RE = re.compile(
    r"\b(?:today|tomorrow|yesterday|tonight|calendar|schedule|meeting|meetings|"
    r"event|events|appointment|appointments|agenda)\b"
    r"|\b(?:this|next|last)\s+(?:week|month|weekend)\b"
    r"|\b(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b"
    r"|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
    re.I,
)
_CALENDAR_FOLLOWUP_RE = re.compile(
    r"\b(?:before that|after that|and before|the previous|the one before|what about that)\b",
    re.I,
)
_DATE_QUESTION_RE = re.compile(
    r"\b(?:"
    r"what(?:'s| is)(?: the)? (?:current )?(?:date|day|time)"
    r"|what (?:day|time|date) is it"
    r"|what day is today"
    r"|which day is (?:it|today)"
    r"|what(?:'s| is) today"
    r"|today'?s date"
    r")\b",
    re.I,
)
_DATE_QUESTION_EXCLUSION_RE = re.compile(
    r"\b(?:calendar|schedule|meeting|meetings|event|events|appointment|appointments|agenda)\b",
    re.I,
)


def _last_turn_used_calendar(history: list[dict]) -> bool:
    for turn in reversed(history):
        if turn.get("role") != "assistant":
            continue
        return any(
            isinstance(card, dict) and card.get("origin") == "calendar"
            for card in (turn.get("cards") or [])
        )
    return False


def _asks_for_the_date(message: str) -> bool:
    """True when the question wants the clock, not the schedule."""
    text = message or ""
    if _DATE_QUESTION_EXCLUSION_RE.search(text):
        return False
    return bool(_DATE_QUESTION_RE.search(text))


def _question_uses_calendar(message: str, history: list[dict]) -> bool:
    """Notes are for a schedule question, or a short follow-up to one."""
    text = message or ""
    if _asks_for_the_date(text):
        return False
    if _SCHEDULE_RE.search(text):
        return True
    return bool(_last_turn_used_calendar(history) and _CALENDAR_FOLLOWUP_RE.search(text))


def _off_calendar_line(history: list[dict]) -> str:
    if not _last_turn_used_calendar(history):
        return ""
    return (
        "This question is not about the calendar. Answer it directly and do not use calendar notes."
    )


async def _prompt_notes(user_id: str, correlation_id: str) -> list[dict[str, str]]:
    today = _now().date()
    start = (today - timedelta(days=7)).isoformat()
    end = (today + timedelta(days=14)).isoformat()
    return await list_notes(user_id, start, end, correlation_id=correlation_id)


_DIRECT_ANSWER = (
    "Reply in plain sentences. State the fact. "
    "When you give a date, copy that date from the statements. "
    "Do not mention the context, the numbered statements, or how the answer was found."
)


def _prompt(
    message: str,
    *,
    context: str,
    context_used: bool,
    notes: list[dict[str, str]],
    attachments: list[ChatFile],
    history: list[dict],
    replay_visual: bool = False,
    memory_name: str = "",
) -> str:
    blocks: list[str] = [_clock_line()]
    focus = _memory_line(memory_name)
    if focus:
        blocks.append(focus)
    if not notes:
        aside = _off_calendar_line(history)
        if aside:
            blocks.append(aside)
    earlier = _history_text(history, replay_visual=replay_visual)
    if earlier:
        blocks.append(earlier)
    if context_used:
        blocks.append(f"Context from the user's documents:\n\n{context}")
    if notes:
        blocks.append(_notes_block(notes))
    for item in attachments:
        if item.visual and not item.text.strip():
            blocks.append(
                f"Attached {item.visual} {item.name} is included for you to see. It is not saved to memory."
            )
            continue
        body = item.text.strip() or "No text could be extracted."
        blocks.append(f"Attached file {item.name} (not saved to memory):\n{body}")
    if not blocks:
        return message
    prompt = "\n\n".join(blocks) + f"\n\nAnswer the user's question: {message}"
    if _asks_for_the_date(message):
        prompt += f"\n\n{_date_authority_line()}"
    return f"{prompt}\n\n{_DIRECT_ANSWER}"


def _notes_block(notes: list[dict[str, str]], now: datetime | None = None) -> str:
    current = _now(now).date()
    written = _written_day(_now(now))
    lines = "\n".join(f"- {note['date']}: {note['note']}" for note in notes)
    return (
        "Calendar notes (not documents). "
        f"Today is {written} ({current.isoformat()}). "
        "A note belongs to today only when its date is that day. "
        f"Each date below is that note's day:\n{lines}"
    )


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
    memory_labels: list[str] = []
    for label in (str(item).strip() for item in sources):
        if label and label not in memory_labels:
            memory_labels.append(label)
    cards: list[tuple[str, Literal["memory", "calendar", "attachment"]]] = [
        (label, "memory") for label in memory_labels
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


def _stored_file(item: ChatFile) -> dict:
    """Keep the file on the turn so a later question can send the same bytes."""
    row = {
        "name": item.name,
        "text": item.text or ("Shown to the model." if item.visual else ""),
    }
    if item.visual and item.data:
        row["kind"] = item.visual
        row["content_base64"] = base64.b64encode(item.data).decode("ascii")
    return row


async def _remember(
    user_id: str,
    session_id: str | None,
    message: str,
    response_text: str,
    cards: list[SourceCard],
    assumptions: list[str],
    attachments: list[ChatFile],
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
                "files": [_stored_file(item) for item in attachments],
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
