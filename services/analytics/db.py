"""MongoDB (or in-memory) store for life_metrics and analytics_snapshots."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from config import get_settings
from logging_setup import logger

_client = None
_database = None
_memory: MemoryStore | None = None

_METRIC_FIELDS = ("sleep_hours", "productivity_score", "meeting_hours", "focus_hours")


class MemoryStore:
    """In-memory metrics used by unit tests (ANALYTICS_STORE=memory)."""

    def __init__(self) -> None:
        self.metrics: dict[tuple[str, str], dict[str, Any]] = {}
        self.by_id: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        self.metrics.clear()
        self.by_id.clear()
        self.snapshots.clear()


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
    return get_settings().ANALYTICS_STORE.lower() == "memory"


async def connect() -> None:
    """Open Motor, or initialize the in-memory store."""
    global _client, _database
    if use_memory():
        memory()
        logger.info("Analytics store: memory")
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
    """Unique (user_id, date) on life_metrics."""
    if use_memory():
        return
    await _db().life_metrics.create_index([("user_id", 1), ("date", 1)], unique=True)
    await _db().analytics_snapshots.create_index([("user_id", 1), ("generated_at", -1)])


def _public_metric(document: dict[str, Any]) -> dict[str, Any]:
    row = {
        "id": document["_id"],
        "user_id": document["user_id"],
        "date": document["date"],
        "updated_at": document.get("updated_at"),
    }
    for field in _METRIC_FIELDS:
        if document.get(field) is not None:
            row[field] = document[field]
    return row


async def upsert_day(user_id: str, day: dict[str, Any]) -> dict[str, Any]:
    """Replace only the fields this ingest inferred for (user_id, date)."""
    date = day["date"]
    if use_memory():
        key = (user_id, date)
        current = dict(memory().metrics.get(key) or {})
        if not current:
            current = {
                "_id": str(uuid.uuid4()),
                "user_id": user_id,
                "date": date,
            }
        for field in _METRIC_FIELDS:
            if field in day:
                current[field] = day[field]
        current["updated_at"] = _now().isoformat()
        memory().metrics[key] = current
        memory().by_id[current["_id"]] = current
        return _public_metric(current)

    existing = await _db().life_metrics.find_one({"user_id": user_id, "date": date})
    update = {field: day[field] for field in _METRIC_FIELDS if field in day}
    update["updated_at"] = _now()
    if existing is None:
        document = {
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "date": date,
            **update,
        }
        await _db().life_metrics.insert_one(document)
        return _public_metric(document)
    await _db().life_metrics.update_one({"_id": existing["_id"]}, {"$set": update})
    existing.update(update)
    return _public_metric(existing)


async def list_metrics(user_id: str) -> list[dict[str, Any]]:
    if use_memory():
        rows = [row for (owner, _), row in memory().metrics.items() if owner == user_id]
        rows.sort(key=lambda row: row["date"])
        return [_public_metric(row) for row in rows]
    cursor = _db().life_metrics.find({"user_id": user_id}).sort("date", 1)
    return [_public_metric(row) async for row in cursor]


async def get_metric(metric_id: str) -> dict[str, Any] | None:
    if use_memory():
        row = memory().by_id.get(metric_id)
        return _public_metric(row) if row else None
    row = await _db().life_metrics.find_one({"_id": metric_id})
    return _public_metric(row) if row else None


async def insert_snapshot(document: dict[str, Any]) -> dict[str, Any]:
    stored = dict(document)
    stored["_id"] = str(uuid.uuid4())
    stored["generated_at"] = _now().isoformat()
    if use_memory():
        memory().snapshots[stored["_id"]] = stored
        return stored
    await _db().analytics_snapshots.insert_one(stored)
    return stored


async def latest_snapshot(user_id: str) -> dict[str, Any] | None:
    if use_memory():
        rows = [row for row in memory().snapshots.values() if row.get("user_id") == user_id]
        if not rows:
            return None
        return max(rows, key=lambda row: row.get("generated_at") or "")
    return await _db().analytics_snapshots.find_one(
        {"user_id": user_id},
        sort=[("generated_at", -1)],
    )


async def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    if use_memory():
        return memory().snapshots.get(snapshot_id)
    return await _db().analytics_snapshots.find_one({"_id": snapshot_id})
