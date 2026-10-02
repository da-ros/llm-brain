"""Lean chat threads and calendar notes. Not document memory."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import db as api_db

_chats: dict[str, dict[str, Any]] = {}
_notes: dict[tuple[str, str], dict[str, Any]] = {}
_turns: list[dict[str, Any]] = []


def reset_memory() -> None:
    _chats.clear()
    _notes.clear()
    _turns.clear()


def _mongo():
    return api_db.database()


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
    return {
        "id": row["_id"],
        "title": row["title"],
        "updated_at": row["updated_at"].isoformat(),
    }


def _public_turn(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": row["role"],
        "text": row["text"],
        "cards": row.get("cards") or [],
        "assumptions": row.get("assumptions") or [],
    }
