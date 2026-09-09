"""In-memory user and document store for the platform-foundation skeleton.

Later modules persist users and documents in MongoDB (GridFS). This store
exists so JWT register/login and per-user isolation can be tested without a
database.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass
class User:
    user_id: str
    email: str
    password_hash: str
    subscription_tier: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Document:
    document_id: str
    user_id: str
    title: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemoryStore:
    """Thread-safe in-memory store keyed by user_id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users_by_email: dict[str, User] = {}
        self._users_by_id: dict[str, User] = {}
        self._documents: dict[str, Document] = {}

    def create_user(self, email: str, password_hash: str, subscription_tier: str) -> User:
        email_key = email.lower()
        with self._lock:
            if email_key in self._users_by_email:
                raise DuplicateEmailError(email)
            user = User(
                user_id=str(uuid4()),
                email=email_key,
                password_hash=password_hash,
                subscription_tier=subscription_tier,
            )
            self._users_by_email[email_key] = user
            self._users_by_id[user.user_id] = user
            return user

    def get_user_by_email(self, email: str) -> User | None:
        with self._lock:
            return self._users_by_email.get(email.lower())

    def get_user_by_id(self, user_id: str) -> User | None:
        with self._lock:
            return self._users_by_id.get(user_id)

    def add_document(self, user_id: str, title: str) -> Document:
        doc = Document(document_id=str(uuid4()), user_id=user_id, title=title)
        with self._lock:
            self._documents[doc.document_id] = doc
        return doc

    def get_document(self, document_id: str) -> Document | None:
        with self._lock:
            return self._documents.get(document_id)

    def list_documents(self, user_id: str) -> list[Document]:
        with self._lock:
            return [doc for doc in self._documents.values() if doc.user_id == user_id]

    def clear(self) -> None:
        with self._lock:
            self._users_by_email.clear()
            self._users_by_id.clear()
            self._documents.clear()


class DuplicateEmailError(Exception):
    """Raised when registering an email that already exists."""

    def __init__(self, email: str) -> None:
        super().__init__(email)
        self.email = email


store = InMemoryStore()
