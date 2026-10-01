"""Local accounts for sign-up and sign-in. Passwords stay hashed."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Any

import db as api_db
from pymongo import ReturnDocument

_users: dict[str, dict[str, Any]] = {}


class AccountExistsError(Exception):
    """Raised when the email is already registered."""


def reset_memory() -> None:
    _users.clear()


def _mongo():
    return api_db.database()


def hash_password(password: str, salt: str | None = None) -> str:
    """PBKDF2 hash stored as salt$hash."""
    used = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), used.encode(), 200_000)
    return f"{used}${digest.hex()}"


def _matches(password: str, stored: str) -> bool:
    salt, _, _digest = stored.partition("$")
    if not salt or not _digest:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def _public(row: dict[str, Any]) -> dict[str, str]:
    return {
        "id": row["user_id"],
        "name": row["name"],
        "email": row["email"],
        "plan": row["plan"],
    }


async def ensure_indexes() -> None:
    database = _mongo()
    if database is None:
        return
    await database.users.create_index("email", unique=True)


async def create_account(name: str, email: str, password: str, plan: str) -> dict[str, str]:
    row = {
        "user_id": str(uuid.uuid4()),
        "name": name,
        "email": email,
        "plan": plan,
        "password_hash": hash_password(password),
    }
    database = _mongo()
    if database is not None:
        existing = await database.users.find_one({"email": email})
        if existing is not None:
            raise AccountExistsError(email)
        await database.users.insert_one(row)
    else:
        if email in _users:
            raise AccountExistsError(email)
        _users[email] = row
    return _public(row)


async def authenticate(email: str, password: str) -> dict[str, str] | None:
    database = _mongo()
    if database is not None:
        row = await database.users.find_one({"email": email})
    else:
        row = _users.get(email)
    if row is None or not _matches(password, row.get("password_hash") or ""):
        return None
    return _public(row)


async def get_account(user_id: str) -> dict[str, str] | None:
    database = _mongo()
    if database is not None:
        row = await database.users.find_one({"user_id": user_id})
    else:
        row = next((item for item in _users.values() if item["user_id"] == user_id), None)
    if row is None:
        return None
    return _public(row)


async def set_plan(user_id: str, plan: str) -> dict[str, str] | None:
    database = _mongo()
    if database is not None:
        result = await database.users.find_one_and_update(
            {"user_id": user_id},
            {"$set": {"plan": plan}},
            return_document=ReturnDocument.AFTER,
        )
        return _public(result) if result else None
    row = next((item for item in _users.values() if item["user_id"] == user_id), None)
    if row is None:
        return None
    row["plan"] = plan
    return _public(row)
