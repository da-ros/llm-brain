"""Chat threads and calendar notes. Not document memory.

The API Router forwards /api/chats and /api/calendar here. Accounts stay
on the router.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

_chats: dict[str, dict[str, Any]] = {}
_notes: dict[tuple[str, str], dict[str, Any]] = {}
_turns: list[dict[str, Any]] = []
_database: Any = None

router = APIRouter(tags=["conversations"])


class TurnBody(BaseModel):
    role: str = "user"
    text: str = ""
    cards: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    files: list[dict[str, Any]] = Field(default_factory=list)


class TurnsBody(BaseModel):
    user_id: str
    turns: list[TurnBody] = Field(default_factory=list)


class TouchBody(BaseModel):
    user_id: str
    message: str = ""


class NoteBody(BaseModel):
    user_id: str
    note: str = ""


def reset_memory() -> None:
    _chats.clear()
    _notes.clear()
    _turns.clear()


def bind(database: Any) -> None:
    """Use this Mongo database. None keeps the in-memory store."""
    global _database
    _database = database


def _mongo() -> Any:
    return _database


async def ensure_indexes() -> None:
    database = _mongo()
    if database is None:
        return
    await database.calendar_notes.create_index([("user_id", 1), ("date", 1)], unique=True)
    await database.chats.create_index([("user_id", 1), ("updated_at", -1)])
    await database.chat_turns.create_index([("user_id", 1), ("chat_id", 1), ("created_at", 1)])


async def list_chats(user_id: str) -> list[dict[str, Any]]:
    database = _mongo()
    if database is not None:
        cursor = database.chats.find({"user_id": user_id}).sort("updated_at", -1)
        rows = await cursor.to_list(length=50)
        return [_public_chat(row) for row in rows]
    rows = [row for row in _chats.values() if row["user_id"] == user_id]
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return [_public_chat(row) for row in rows]


async def rename_chat(user_id: str, chat_id: str, title: str) -> dict[str, Any] | None:
    """Set an owned chat's title. None when the caller does not own it."""
    cleaned = " ".join(title.split())[:80]
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title is required")
    if not await _owns_chat(user_id, chat_id):
        return None
    now = datetime.now(UTC)
    database = _mongo()
    if database is not None:
        await database.chats.update_one(
            {"_id": chat_id, "user_id": user_id},
            {"$set": {"title": cleaned, "updated_at": now}},
        )
        row = await database.chats.find_one({"_id": chat_id, "user_id": user_id})
        return _public_chat(row)
    row = _chats[chat_id]
    row["title"] = cleaned
    row["updated_at"] = now
    return _public_chat(row)


async def delete_chat(user_id: str, chat_id: str) -> bool:
    """Remove one owned chat and its turns. False when the caller does not own it."""
    if not await _owns_chat(user_id, chat_id):
        return False
    database = _mongo()
    if database is not None:
        await database.chat_turns.delete_many({"user_id": user_id, "chat_id": chat_id})
        await database.chats.delete_one({"_id": chat_id, "user_id": user_id})
        return True
    _chats.pop(chat_id, None)
    _turns[:] = [
        row for row in _turns if not (row["user_id"] == user_id and row["chat_id"] == chat_id)
    ]
    return True


async def create_chat(user_id: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    row = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": "New chat",
        "created_at": now,
        "updated_at": now,
    }
    database = _mongo()
    if database is not None:
        await database.chats.insert_one(row)
    else:
        _chats[row["_id"]] = row
    return _public_chat(row)


async def touch_chat(user_id: str, chat_id: str, message: str) -> None:
    """Name a still-untitled thread from the first question and mark it active."""
    title = " ".join(message.split())[:48] or "New chat"
    now = datetime.now(UTC)
    database = _mongo()
    if database is not None:
        await database.chats.update_one(
            {"_id": chat_id, "user_id": user_id},
            {"$set": {"updated_at": now}},
        )
        await database.chats.update_one(
            {"_id": chat_id, "user_id": user_id, "title": "New chat"},
            {"$set": {"title": title}},
        )
        return
    row = _chats.get(chat_id)
    if row and row["user_id"] == user_id:
        row["updated_at"] = now
        if row["title"] == "New chat":
            row["title"] = title


async def append_turns(user_id: str, chat_id: str, turns: list[dict[str, Any]]) -> None:
    """Store a question and its answer on a chat the caller owns."""
    if not turns or not await _owns_chat(user_id, chat_id):
        return
    now = datetime.now(UTC)
    rows = [
        {
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "chat_id": chat_id,
            "role": turn.get("role") or "user",
            "text": turn.get("text") or "",
            "cards": list(turn.get("cards") or []),
            "assumptions": list(turn.get("assumptions") or []),
            "files": list(turn.get("files") or []),
            "created_at": now,
            "seq": index,
        }
        for index, turn in enumerate(turns)
    ]
    database = _mongo()
    if database is not None:
        await database.chat_turns.insert_many(rows)
        return
    _turns.extend(rows)


async def list_turns(user_id: str, chat_id: str) -> list[dict[str, Any]] | None:
    """Turns for one owned chat. None when the chat belongs to someone else."""
    if not await _owns_chat(user_id, chat_id):
        return None
    database = _mongo()
    if database is not None:
        cursor = database.chat_turns.find({"user_id": user_id, "chat_id": chat_id}).sort(
            [("created_at", 1), ("seq", 1)]
        )
        rows = await cursor.to_list(length=500)
        return [_public_turn(row) for row in rows]
    rows = [row for row in _turns if row["user_id"] == user_id and row["chat_id"] == chat_id]
    rows.sort(key=lambda row: (row["created_at"], row["seq"]))
    return [_public_turn(row) for row in rows]


async def chat_history(user_id: str, chat_id: str) -> list[dict[str, Any]] | None:
    """Prior questions, answers, and file text. None when the chat is not owned."""
    if not await _owns_chat(user_id, chat_id):
        return None
    database = _mongo()
    if database is not None:
        cursor = database.chat_turns.find({"user_id": user_id, "chat_id": chat_id}).sort(
            [("created_at", 1), ("seq", 1)]
        )
        rows = await cursor.to_list(length=500)
    else:
        rows = [row for row in _turns if row["user_id"] == user_id and row["chat_id"] == chat_id]
        rows.sort(key=lambda row: (row["created_at"], row["seq"]))
    return [
        {"role": row["role"], "text": row["text"], "files": row.get("files") or []} for row in rows
    ]


async def _owns_chat(user_id: str, chat_id: str) -> bool:
    database = _mongo()
    if database is not None:
        row = await database.chats.find_one({"_id": chat_id, "user_id": user_id})
        return row is not None
    row = _chats.get(chat_id)
    return bool(row and row["user_id"] == user_id)


async def list_notes(user_id: str, start: str, end: str) -> list[dict[str, str]]:
    database = _mongo()
    if database is not None:
        cursor = database.calendar_notes.find(
            {"user_id": user_id, "date": {"$gte": start, "$lte": end}}
        ).sort("date", 1)
        rows = await cursor.to_list(length=62)
        return [{"date": row["date"], "note": row["note"]} for row in rows if row.get("note")]
    rows = [
        row
        for (owner, _date), row in _notes.items()
        if owner == user_id and start <= row["date"] <= end and row.get("note")
    ]
    rows.sort(key=lambda row: row["date"])
    return [{"date": row["date"], "note": row["note"]} for row in rows]


async def put_note(user_id: str, day: str, note: str) -> None:
    text = note.strip()
    database = _mongo()
    if not text:
        if database is not None:
            await database.calendar_notes.delete_one({"user_id": user_id, "date": day})
        else:
            _notes.pop((user_id, day), None)
        return
    now = datetime.now(UTC)
    row = {"user_id": user_id, "date": day, "note": text, "updated_at": now}
    if database is not None:
        await database.calendar_notes.update_one(
            {"user_id": user_id, "date": day},
            {"$set": row},
            upsert=True,
        )
        return
    _notes[(user_id, day)] = row


def _public_chat(row: dict[str, Any]) -> dict[str, Any]:
    updated = row["updated_at"]
    return {
        "id": row["_id"],
        "title": row["title"],
        "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else str(updated),
    }


def _public_turn(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": row["role"],
        "text": row["text"],
        "cards": row.get("cards") or [],
        "assumptions": row.get("assumptions") or [],
    }


@router.get("/chats")
async def get_chats(user_id: str = Query(...)) -> dict[str, Any]:
    return {"chats": await list_chats(user_id)}


@router.post("/chats", status_code=status.HTTP_201_CREATED)
async def post_chat(user_id: str = Query(...)) -> dict[str, Any]:
    return await create_chat(user_id)


class RenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=80)


@router.patch("/chats/{chat_id}")
async def patch_chat(chat_id: str, body: RenameBody, user_id: str = Query(...)) -> dict[str, Any]:
    renamed = await rename_chat(user_id, chat_id, body.title)
    if renamed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return renamed


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_chat(chat_id: str, user_id: str = Query(...)) -> Response:
    if not await delete_chat(user_id, chat_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/chats/{chat_id}/turns")
async def get_turns(chat_id: str, user_id: str = Query(...)) -> dict[str, Any]:
    turns = await list_turns(user_id, chat_id)
    if turns is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return {"turns": turns}


@router.get("/chats/{chat_id}/history")
async def get_history(chat_id: str, user_id: str = Query(...)) -> dict[str, Any]:
    rows = await chat_history(user_id, chat_id)
    return {"history": rows or []}


@router.post(
    "/chats/{chat_id}/touch", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def post_touch(chat_id: str, body: TouchBody) -> Response:
    await touch_chat(body.user_id, chat_id, body.message)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/chats/{chat_id}/turns", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def post_turns(chat_id: str, body: TurnsBody) -> Response:
    await append_turns(body.user_id, chat_id, [turn.model_dump() for turn in body.turns])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notes")
async def get_notes(
    user_id: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
) -> dict[str, Any]:
    return {"notes": await list_notes(user_id, start, end)}


@router.put("/notes/{day}")
async def save_note(day: str, body: NoteBody) -> dict[str, bool]:
    await put_note(body.user_id, day, body.note)
    return {"saved": bool(body.note.strip())}
