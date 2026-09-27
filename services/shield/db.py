"""MongoDB (or in-memory) store for shield_incidents."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from config import get_settings
from logging_setup import logger

_client = None
_database = None
_memory: MemoryStore | None = None


class MemoryStore:
    """In-memory incidents used by unit tests (SHIELD_STORE=memory)."""

    def __init__(self) -> None:
        self.by_correlation: dict[str, dict[str, Any]] = {}
        self.by_id: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        self.by_correlation.clear()
        self.by_id.clear()


def _now() -> datetime:
    return datetime.now(UTC)


def memory() -> MemoryStore:
    global _memory
    if _memory is None:
        _memory = MemoryStore()
    return _memory


def reset_memory() -> None:
    """Clear the in-memory store (tests)."""
    memory().reset()


def use_memory() -> bool:
    return get_settings().SHIELD_STORE.lower() == "memory"


async def connect() -> None:
    """Open Motor, or initialize the in-memory store."""
    global _client, _database
    if use_memory():
        memory()
        logger.info("Shield store: memory")
        return
    from motor.motor_asyncio import AsyncIOMotorClient

    settings = get_settings()
    _client = AsyncIOMotorClient(settings.MONGODB_URI)
    _database = _client[settings.MONGODB_DB]
    logger.info("Connected to MongoDB")


async def disconnect() -> None:
    """Close Motor."""
    global _client, _database
    if _client is not None:
        _client.close()
    _client = None
    _database = None


def _db():
    if _database is None:
        raise RuntimeError("MongoDB is not connected")
    return _database


async def ensure_indexes() -> None:
    """Unique correlation_id plus a user_id index."""
    if use_memory():
        return
    database = _db()
    await database.shield_incidents.create_index("correlation_id", unique=True)
    await database.shield_incidents.create_index("user_id")
    logger.info("Ensured shield_incidents indexes (unique correlation_id, user_id)")


def _serialize(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    payload = dict(document)
    if "_id" in payload:
        payload["_id"] = str(payload["_id"])
    created = payload.get("created_at")
    if isinstance(created, datetime):
        payload["created_at"] = created.isoformat()
    return payload


async def find_by_correlation(correlation_id: str) -> dict[str, Any] | None:
    if use_memory():
        return _serialize(memory().by_correlation.get(correlation_id))
    document = await _db().shield_incidents.find_one({"correlation_id": correlation_id})
    return _serialize(document)


async def find_by_id(incident_id: str) -> dict[str, Any] | None:
    if use_memory():
        return _serialize(memory().by_id.get(incident_id))
    document = await _db().shield_incidents.find_one({"_id": incident_id})
    return _serialize(document)


async def list_for_user(user_id: str) -> list[dict[str, Any]]:
    if use_memory():
        rows = [row for row in memory().by_id.values() if row.get("user_id") == user_id]
        rows.sort(key=lambda row: row.get("created_at") or _now(), reverse=True)
        return [row for row in (_serialize(item) for item in rows) if row]
    cursor = _db().shield_incidents.find({"user_id": user_id}).sort("created_at", -1)
    return [row for row in (_serialize(item) for item in await cursor.to_list(length=200)) if row]


async def insert_incident(document: dict[str, Any]) -> dict[str, Any]:
    """Insert one alert. A duplicate correlation_id returns the stored row."""
    correlation_id = document["correlation_id"]
    existing = await find_by_correlation(correlation_id)
    if existing is not None:
        return existing
    now = _now()
    incident_id = str(uuid.uuid4())
    record = {
        **document,
        "_id": incident_id,
        "created_at": now,
    }
    if use_memory():
        stored = dict(record)
        memory().by_correlation[correlation_id] = stored
        memory().by_id[incident_id] = stored
        return _serialize(stored) or stored
    await _db().shield_incidents.insert_one(record)
    return _serialize(record) or record
