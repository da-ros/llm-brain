"""MongoDB (or in-memory) store for interactions, feedback, and weekly batches."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from config import get_settings
from logging_setup import logger

_client = None
_database = None
_memory: MemoryStore | None = None


class MemoryStore:
    """In-memory collections used by unit tests (AGENTS_STORE=memory)."""

    def __init__(self) -> None:
        self.interactions: dict[str, dict[str, Any]] = {}
        self.feedback: dict[str, dict[str, Any]] = {}
        self.batches: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        self.interactions.clear()
        self.feedback.clear()
        self.batches.clear()


def _now() -> datetime:
    return datetime.now(UTC)


def _iso_week(moment: datetime | None = None) -> str:
    value = moment or _now()
    year, week, _ = value.isocalendar()
    return f"{year}-W{week:02d}"


def memory() -> MemoryStore:
    global _memory
    if _memory is None:
        _memory = MemoryStore()
    return _memory


def reset_memory() -> None:
    """Clear the in-memory store (tests)."""
    memory().reset()


def use_memory() -> bool:
    return get_settings().AGENTS_STORE.lower() == "memory"


async def connect() -> None:
    """Open Motor, or initialize the in-memory store."""
    global _client, _database
    if use_memory():
        memory()
        logger.info("Agents store: memory")
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
    """Unique correlation_id, weekly batch identity, TTL on feedback logs."""
    if use_memory():
        return
    settings = get_settings()
    database = _db()
    await database.agent_interactions.create_index("correlation_id", unique=True)
    await database.agent_feedback.create_index("correlation_id", unique=True)
    await database.agent_feedback.create_index("expires_at", expireAfterSeconds=0)
    await database.finetune_batches.create_index(
        [("user_id", 1), ("iso_week", 1)],
        unique=True,
    )
    logger.info(
        "Ensured agent indexes (TTL=%s days on agent_feedback)",
        settings.TASK_STATUS_TTL_DAYS,
    )


def _serialize(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if document is None:
        return None
    payload = dict(document)
    if "_id" in payload:
        payload["_id"] = str(payload["_id"])
    return payload


async def upsert_interaction(document: dict[str, Any]) -> dict[str, Any]:
    """Insert one interaction; idempotent on correlation_id."""
    correlation_id = document["correlation_id"]
    now = _now()
    record = {
        **document,
        "created_at": document.get("created_at") or now,
        "updated_at": now,
    }
    if use_memory():
        existing = memory().interactions.get(correlation_id)
        if existing is not None:
            return dict(existing)
        record["_id"] = correlation_id
        memory().interactions[correlation_id] = dict(record)
        return dict(record)

    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    collection = _db().agent_interactions
    try:
        await collection.insert_one({"_id": correlation_id, **record})
        stored = await collection.find_one({"correlation_id": correlation_id})
        return _serialize(stored) or record
    except DuplicateKeyError:
        stored = await collection.find_one_and_update(
            {"correlation_id": correlation_id},
            {"$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return _serialize(stored) or record


async def find_interaction(
    correlation_id: str, user_id: str | None = None
) -> dict[str, Any] | None:
    if use_memory():
        doc = memory().interactions.get(correlation_id)
        if doc is None:
            return None
        if user_id is not None and doc.get("user_id") != user_id:
            return None
        return dict(doc)
    query: dict[str, Any] = {"correlation_id": correlation_id}
    if user_id is not None:
        query["user_id"] = user_id
    return _serialize(await _db().agent_interactions.find_one(query))


async def upsert_feedback(document: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    now = _now()
    correlation_id = document["correlation_id"]
    record = {
        **document,
        "created_at": document.get("created_at") or now,
        "expires_at": now + timedelta(days=settings.TASK_STATUS_TTL_DAYS),
    }
    if use_memory():
        record["_id"] = correlation_id
        memory().feedback[correlation_id] = dict(record)
        return dict(record)

    from pymongo import ReturnDocument

    stored = await _db().agent_feedback.find_one_and_update(
        {"correlation_id": correlation_id},
        {"$set": record},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return _serialize(stored) or record


async def find_feedback(correlation_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    if use_memory():
        doc = memory().feedback.get(correlation_id)
        if doc is None:
            return None
        if user_id is not None and doc.get("user_id") != user_id:
            return None
        return dict(doc)
    query: dict[str, Any] = {"correlation_id": correlation_id}
    if user_id is not None:
        query["user_id"] = user_id
    return _serialize(await _db().agent_feedback.find_one(query))


async def append_batch_item(
    *,
    user_id: str,
    item: dict[str, Any],
    min_items: int | None = None,
) -> dict[str, Any]:
    """Append an eligible turn to this user's ISO-week batch (no duplicates)."""
    settings = get_settings()
    threshold = min_items if min_items is not None else settings.BATCH_MIN_ITEMS
    iso_week = _iso_week()
    correlation_id = item["correlation_id"]
    now = _now()

    if use_memory():
        store = memory()
        batch = next(
            (
                doc
                for doc in store.batches.values()
                if doc.get("user_id") == user_id and doc.get("iso_week") == iso_week
            ),
            None,
        )
        if batch is None:
            batch_id = str(uuid.uuid4())
            batch = {
                "_id": batch_id,
                "user_id": user_id,
                "iso_week": iso_week,
                "items": [],
                "status": "accumulating",
                "dataset_path": None,
                "job_id": None,
                "created_at": now,
                "updated_at": now,
            }
            store.batches[batch_id] = batch
        if batch["status"] == "submitted":
            return dict(batch)
        items = list(batch.get("items") or [])
        if not any(entry.get("correlation_id") == correlation_id for entry in items):
            items.append(item)
        batch["items"] = items
        if batch["status"] != "submitted":
            batch["status"] = "ready" if len(items) >= threshold else "accumulating"
        batch["updated_at"] = now
        return dict(batch)

    collection = _db().finetune_batches
    existing = await collection.find_one({"user_id": user_id, "iso_week": iso_week})
    if existing is None:
        doc = {
            "user_id": user_id,
            "iso_week": iso_week,
            "items": [item],
            "status": "ready" if threshold <= 1 else "accumulating",
            "dataset_path": None,
            "job_id": None,
            "created_at": now,
            "updated_at": now,
        }
        if len(doc["items"]) >= threshold:
            doc["status"] = "ready"
        result = await collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc) or doc

    if existing.get("status") == "submitted":
        return _serialize(existing) or existing

    items = list(existing.get("items") or [])
    if not any(entry.get("correlation_id") == correlation_id for entry in items):
        items.append(item)
    status = "ready" if len(items) >= threshold else "accumulating"
    await collection.update_one(
        {"_id": existing["_id"]},
        {"$set": {"items": items, "status": status, "updated_at": now}},
    )
    existing["items"] = items
    existing["status"] = status
    existing["updated_at"] = now
    return _serialize(existing) or existing


async def find_batch(batch_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    if use_memory():
        doc = memory().batches.get(batch_id)
        if doc is None:
            return None
        if user_id is not None and doc.get("user_id") != user_id:
            return None
        return dict(doc)
    from bson import ObjectId
    from bson.errors import InvalidId

    query: dict[str, Any]
    try:
        query = {"_id": ObjectId(batch_id)}
    except InvalidId:
        query = {"_id": batch_id}
    if user_id is not None:
        query["user_id"] = user_id
    stored = await _db().finetune_batches.find_one(query)
    if stored is None and user_id is not None:
        return None
    if stored is None:
        stored = await _db().finetune_batches.find_one({"_id": batch_id})
    return _serialize(stored)


async def list_batches(user_id: str) -> list[dict[str, Any]]:
    if use_memory():
        return [dict(doc) for doc in memory().batches.values() if doc.get("user_id") == user_id]
    cursor = _db().finetune_batches.find({"user_id": user_id})
    return [_serialize(doc) or doc async for doc in cursor]


async def update_batch(
    batch_id: str, updates: dict[str, Any], user_id: str | None = None
) -> dict[str, Any] | None:
    payload = {**updates, "updated_at": _now()}
    if use_memory():
        doc = memory().batches.get(batch_id)
        if doc is None:
            return None
        if user_id is not None and doc.get("user_id") != user_id:
            return None
        doc.update(payload)
        return dict(doc)
    from bson import ObjectId
    from bson.errors import InvalidId
    from pymongo import ReturnDocument

    query: dict[str, Any]
    try:
        query = {"_id": ObjectId(batch_id)}
    except InvalidId:
        query = {"_id": batch_id}
    if user_id is not None:
        query["user_id"] = user_id
    stored = await _db().finetune_batches.find_one_and_update(
        query,
        {"$set": payload},
        return_document=ReturnDocument.AFTER,
    )
    return _serialize(stored)
