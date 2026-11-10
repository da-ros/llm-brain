"""RAG Service — LangChain retrieval facade (chunk, embed, search, inject).

Depends on VectorStore and Embedder abstractions (DIP). Per-user isolation
is enforced on every query via user_id.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from config import get_settings
from document_store import DocumentStore, document_store
from embeddings import Embedder, create_embedder
from langchain_text_splitters import RecursiveCharacterTextSplitter
from logging_setup import log_with_correlation
from vector_store import VectorStore, create_vector_store

IMAGE_TYPES = {"image", "image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEO_TYPES = {"video", "video/mp4", "video/webm", "video/quicktime"}


def _clip_summary(texts: list[str], limit: int = 250) -> str:
    parts = [" ".join(text.split()) for text in texts if text and text.strip()]
    compact = "; ".join(parts)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


_NOTE_KEYS = ("source notes", "source_notes", "source_note")
_BARE_OBJECTS = {"thing", "a thing", "things"}
_SAME_NOTE_LIMIT = 24
_WIDE_NOTE_MARKERS = ("section", "table", "header", "issue log", "voice note")
_TRIPLES_ROOT = Path("/app/data/triples")


def _sentence(triple: dict) -> str:
    return " ".join(
        str(triple.get(key) or "").strip()
        for key in ("subject", "predicate", "object")
        if str(triple.get(key) or "").strip()
    )


def _source_note(triple: dict) -> str:
    metadata = triple.get("metadata") if isinstance(triple.get("metadata"), dict) else {}
    for key in _NOTE_KEYS:
        value = metadata.get(key)
        if value:
            return " ".join(str(value).split())
    return ""


def _bare_object(value: Any) -> bool:
    return str(value or "").strip().lower().strip(".,;") in _BARE_OBJECTS


def _row_note(note: str) -> bool:
    """A dated row travels together. A section, table, or whole file does not."""
    text = (note or "").lower()
    return bool(text) and not any(marker in text for marker in _WIDE_NOTE_MARKERS)


_ROW_DATE_NOTE = re.compile(r"^date:\s*\d{4}-\d{2}-\d{2}\b", re.I)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _kept_triples(triples: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for triple in triples:
        if not isinstance(triple, dict) or _bare_object(triple.get("object")):
            continue
        if _sentence(triple):
            kept.append(triple)
    return kept


def _join_row(group: list[dict]) -> str:
    return "\n".join(_sentence(triple) for triple in group)


def _event_date_row(triple: dict) -> bool:
    subject = str(triple.get("subject") or "").strip()
    note = _source_note(triple).lower()
    return bool(_ISO_DATE.match(subject) and "table" in note and "header" not in note)


def row_passages(triples: list[dict]) -> list[str]:
    """One passage per spreadsheet row. A prose fact stays its own sentence.

    A CSV row shares a date note. An issue row starts at has_date. An event
    table row starts at a date and keeps the outcome lines under it.
    """
    kept = _kept_triples(triples)
    if not kept:
        return []
    if sum(1 for triple in kept if _ROW_DATE_NOTE.match(_source_note(triple))) >= 2:
        return _passages_by_date_note(kept)
    if sum(1 for triple in kept if str(triple.get("predicate") or "").strip() == "has_date") >= 2:
        return _passages_by_has_date(kept)
    if sum(1 for triple in kept if _event_date_row(triple)) >= 2:
        return _passages_by_event_date(kept)
    return [_sentence(triple) for triple in kept]


def _passages_by_date_note(triples: list[dict]) -> list[str]:
    groups: list[list[dict]] = []
    buckets: dict[str, list[dict]] = {}
    for triple in triples:
        note = _source_note(triple)
        if _ROW_DATE_NOTE.match(note):
            if note not in buckets:
                buckets[note] = []
                groups.append(buckets[note])
            buckets[note].append(triple)
        else:
            groups.append([triple])
    return [_join_row(group) for group in groups]


def _passages_by_has_date(triples: list[dict]) -> list[str]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for triple in triples:
        if str(triple.get("predicate") or "").strip() == "has_date" and current:
            groups.append(current)
            current = []
        current.append(triple)
    if current:
        groups.append(current)
    return [_join_row(group) for group in groups]


def _passages_by_event_date(triples: list[dict]) -> list[str]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for triple in triples:
        note = _source_note(triple).lower()
        if _event_date_row(triple):
            if current:
                groups.append(current)
            current = [triple]
            continue
        if current and "table" in note and "header" not in note:
            current.append(triple)
            continue
        if current:
            groups.append(current)
            current = []
        groups.append([triple])
    if current:
        groups.append(current)
    return [_join_row(group) for group in groups]


def _safe_id(value: Any) -> str:
    text = str(value or "")
    if not text or "/" in text or "\\" in text or text in {".", ".."}:
        return ""
    return text


def _load_note_triples(user_id: str, doc_id: str) -> list[dict]:
    """Read the JSONL for one indexed file. Missing files contribute no siblings."""
    path = _TRIPLES_ROOT / user_id / f"{doc_id}.jsonl"
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _locate_triple(triples: list[dict], triple_index: int | None, text: str) -> dict | None:
    """Find the stored row for a search hit.

    Older indexes count every JSONL row. Newer indexes skip an object that is
    only "thing", so the same triple_index can mean either list.
    """
    usable = [triple for triple in triples if _sentence(triple)]
    kept = [triple for triple in usable if not _bare_object(triple.get("object"))]
    if triple_index is not None and triple_index >= 0:
        if triple_index < len(usable) and _sentence(usable[triple_index]) == text:
            return usable[triple_index]
        if triple_index < len(kept) and _sentence(kept[triple_index]) == text:
            return kept[triple_index]
    matches = [triple for triple in kept if _sentence(triple) == text]
    if len(matches) == 1:
        return matches[0]
    return None


def expand_same_note(
    results: list[dict[str, Any]],
    read_triples=_load_note_triples,
) -> list[dict[str, Any]]:
    """Keep each nearest fact, and add the other facts written under its note.

    Search stays on the single fact. The note is the passage that fact was
    taken from, so the model reads the whole row rather than one column.
    """
    loaded: dict[tuple[str, str], list[dict]] = {}
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def remember(item: dict[str, Any]) -> bool:
        metadata = item.get("metadata") or {}
        text = str(item.get("document") or "")
        key = (str(metadata.get("doc_id") or ""), str(metadata.get("source") or ""), text)
        if not text or key in seen:
            return False
        seen.add(key)
        output.append(item)
        return True

    for result in results:
        remember(result)
        metadata = result.get("metadata") or {}
        text = str(result.get("document") or "")
        user_id = _safe_id(metadata.get("user_id"))
        doc_id = _safe_id(metadata.get("doc_id"))
        if not user_id or not doc_id or not text or "\n" in text:
            continue
        try:
            triple_index = int(metadata.get("triple_index"))
        except (TypeError, ValueError):
            triple_index = None
        if triple_index is not None and triple_index < 0:
            continue
        cache_key = (user_id, doc_id)
        if cache_key not in loaded:
            loaded[cache_key] = read_triples(user_id, doc_id)
        found = _locate_triple(loaded[cache_key], triple_index, text)
        if found is None:
            continue
        note = _source_note(found)
        if not _row_note(note):
            continue
        added = 0
        for triple in loaded[cache_key]:
            if _source_note(triple) != note or _bare_object(triple.get("object")):
                continue
            sentence = _sentence(triple)
            if not sentence or sentence == text:
                continue
            companion = {
                "id": f"{result.get('id') or doc_id}_note_{added}",
                "metadata": {
                    "user_id": user_id,
                    "doc_id": doc_id,
                    "gridfs_id": metadata.get("gridfs_id") or "",
                    "modality": "text",
                    "source": metadata.get("source")
                    or (triple.get("metadata") or {}).get("source_file")
                    or "",
                    "same_note": True,
                },
                "distance": result.get("distance"),
                "document": sentence,
            }
            if remember(companion):
                added += 1
            if added >= _SAME_NOTE_LIMIT:
                break
    return output


def _remove_triples_file(triples_path: str, user_id: str) -> None:
    """Delete the JSONL for this user when the path stays inside the triples directory."""
    if not triples_path or not user_id or "/" in user_id or user_id in {".", ".."}:
        return
    root = (Path("/app/data/triples") / user_id).resolve()
    try:
        candidate = Path(triples_path).resolve()
    except OSError:
        return
    if candidate.parent != root or candidate.suffix != ".jsonl":
        return
    candidate.unlink(missing_ok=True)


def modality_from_type(doc_type: str | None) -> str:
    """Map a document type / MIME to text | image | video."""
    value = (doc_type or "text").lower()
    if value in IMAGE_TYPES or value.startswith("image/"):
        return "image"
    if value in VIDEO_TYPES or value.startswith("video/"):
        return "video"
    return "text"


class RAGService:
    """Facade: ingest JSONL triples, Top-k search, LLM context injection."""

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        store: DocumentStore | None = None,
    ) -> None:
        settings = get_settings()
        self._vector_store = vector_store
        self._embedder = embedder
        self._embedder_lock = threading.Lock()
        self._document_store = store
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    @property
    def vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = create_vector_store()
        return self._vector_store

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            with self._embedder_lock:
                if self._embedder is None:
                    self._embedder = create_embedder()
        return self._embedder

    @property
    def documents(self) -> DocumentStore:
        if self._document_store is None:
            self._document_store = document_store
        return self._document_store

    def embed_text(self, text: str) -> list[float]:
        """Generate a 2048-dim embedding for text (shared multimodal space)."""
        return self.embedder.embed_text(text)

    def embed_query(self, modality: str, *, text: str = "", payload: bytes = b"") -> list[float]:
        """Query vector only. Callers must not write the result to Chroma."""
        if modality == "text":
            return self.embedder.embed_text(text)
        if modality == "image":
            return self.embedder.embed_image(payload)
        if modality == "video":
            vector = self.embedder.embed_video(payload)
            if not vector:
                raise ValueError("video has no decodable frames")
            return vector
        raise ValueError(f"unsupported modality: {modality}")

    def chunk_text(self, text: str) -> list[str]:
        """Split text with RecursiveCharacterTextSplitter (1000 / 200)."""
        if not text:
            return []
        if len(text) <= get_settings().RAG_CHUNK_SIZE:
            return [text]
        return self._splitter.split_text(text)

    async def ingest_triples(
        self,
        user_id: str,
        doc_id: str,
        triples_path: str,
        *,
        gridfs_id: str = "",
        doc_type: str = "text",
        filename: str = "",
        correlation_id: str = "no-id",
    ) -> int:
        """Read Frame 2 JSONL, chunk, embed (2048-dim), encrypt, store in Chroma."""
        path = Path(triples_path)
        if not path.exists():
            log_with_correlation(
                correlation_id,
                "warning",
                f"JSONL not found: {triples_path}",
            )
            return 0

        parsed: list[dict] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    triple = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(triple, dict):
                    parsed.append(triple)
        texts = row_passages(parsed)
        source_name = filename or str(
            ((parsed[0].get("metadata") or {}) if parsed else {}).get("source_file") or ""
        )

        if not texts:
            return 0

        modality = modality_from_type(doc_type)
        stored_name = (source_name or "").strip()
        chunks: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []
        for index, text in enumerate(texts):
            for chunk_index, chunk in enumerate(self.chunk_text(text)):
                chunks.append(chunk)
                metadatas.append(
                    {
                        "user_id": user_id,
                        "doc_id": doc_id,
                        "gridfs_id": gridfs_id,
                        "modality": "text",
                        "triple_index": index,
                        "chunk_index": chunk_index,
                        "source": stored_name,
                    }
                )
                ids.append(f"{user_id}_{doc_id}_row{index}_chunk{chunk_index}")

        binary_vector: list[float] | None = None
        if modality in {"image", "video"} and gridfs_id:
            payload = await self.documents.get_binary(gridfs_id, user_id)
            if payload and modality == "image":
                binary_vector = self.embedder.embed_image(payload)
            elif payload and modality == "video":
                binary_vector = self.embedder.embed_video(payload)
                if binary_vector is None:
                    log_with_correlation(
                        correlation_id,
                        "warning",
                        "Video has no decodable frames; keeping the description triples only",
                    )
            if binary_vector is not None:
                chunks.append("\n".join(texts))
                metadatas.append(
                    {
                        "user_id": user_id,
                        "doc_id": doc_id,
                        "gridfs_id": gridfs_id,
                        "modality": modality,
                        "triple_index": -1,
                        "chunk_index": 0,
                        "source": stored_name,
                    }
                )
                ids.append(f"{user_id}_{doc_id}_{modality}")
        embeddings = [self.embed_text(chunk) for chunk in chunks]
        if binary_vector is not None:
            embeddings[-1] = binary_vector

        log_with_correlation(
            correlation_id,
            "debug",
            f"Embedding {len(embeddings)} chunks ({get_settings().EMBEDDING_DIM} dims)",
        )
        await self.vector_store.add(embeddings, metadatas, ids, documents=chunks)

        try:
            await self.documents.insert_document(
                user_id=user_id,
                doc_type=modality,
                gridfs_id=gridfs_id,
                triples_path=triples_path,
                correlation_id=correlation_id,
                filename=stored_name,
                content_type=doc_type,
                summary=_clip_summary(texts),
                source_id=doc_id,
            )
        except Exception as exc:
            log_with_correlation(
                correlation_id,
                "warning",
                f"Document index insert skipped: {exc}",
            )

        return len(texts)

    async def replace_row_vectors(
        self,
        user_id: str,
        doc_id: str,
        triples_path: str,
        *,
        filename: str = "",
        correlation_id: str = "no-id",
    ) -> int:
        """Replace one file's sentence vectors with one vector per spreadsheet row.

        The JSONL on disk is left as one triple per line. The catalog row stays.
        """
        path = Path(triples_path)
        if not path.is_file():
            log_with_correlation(correlation_id, "warning", f"JSONL not found: {triples_path}")
            return 0
        parsed: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                triple = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(triple, dict):
                parsed.append(triple)
        texts = row_passages(parsed)
        if not texts:
            return 0
        removed = await self.delete_document_embeddings(doc_id, user_id)
        stored_name = (
            filename
            or str(((parsed[0].get("metadata") or {}) if parsed else {}).get("source_file") or "")
        ).strip()
        chunks: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []
        for index, text in enumerate(texts):
            for chunk_index, chunk in enumerate(self.chunk_text(text)):
                chunks.append(chunk)
                metadatas.append(
                    {
                        "user_id": user_id,
                        "doc_id": doc_id,
                        "gridfs_id": "",
                        "modality": "text",
                        "triple_index": index,
                        "chunk_index": chunk_index,
                        "source": stored_name,
                    }
                )
                ids.append(f"{user_id}_{doc_id}_row{index}_chunk{chunk_index}")
        embeddings = [self.embed_text(chunk) for chunk in chunks]
        await self.vector_store.add(embeddings, metadatas, ids, documents=chunks)
        log_with_correlation(
            correlation_id,
            "info",
            f"Replaced {removed} vectors with {len(chunks)} row passages for {stored_name}",
        )
        return len(texts)

    async def semantic_search(
        self,
        query: str,
        user_id: str,
        k: int | None = None,
        *,
        correlation_id: str = "no-id",
    ) -> list[dict[str, Any]]:
        """Embed the query and return Top-k matches, plus the rest of each match's note."""
        if k is None:
            k = get_settings().RAG_TOP_K
        log_with_correlation(
            correlation_id,
            "debug",
            f"Searching Chroma with k={k}, user_id={user_id}",
        )
        query_embedding = self.embed_text(query)
        found = await self.vector_store.search(query_embedding, k, user_id)
        return expand_same_note(found)

    async def top_k_retrieval(
        self,
        query: str,
        user_id: str,
        k: int | None = None,
        *,
        correlation_id: str = "no-id",
    ) -> list[dict[str, Any]]:
        """LangChain-style Top-k retrieval (same as semantic_search)."""
        return await self.semantic_search(query, user_id, k, correlation_id=correlation_id)

    async def context_injection(
        self,
        query: str,
        user_id: str,
        *,
        correlation_id: str = "no-id",
    ) -> str:
        """Format Top-k chunks as LLM context. Empty corpus → explicit message."""
        results = await self.semantic_search(query, user_id, correlation_id=correlation_id)
        if not results:
            log_with_correlation(correlation_id, "info", "No relevant context found")
            return "No relevant context found in your documents."

        parts: list[str] = []
        for index, result in enumerate(results, 1):
            meta = result.get("metadata") or {}
            text = result.get("document") or meta.get("chunk_text") or meta.get("text") or ""
            source = meta.get("source") or meta.get("gridfs_id") or "unknown"
            parts.append(f"[{index}] {text} (source: {source})")
        return "\n".join(parts)

    async def delete_document_embeddings(self, doc_id: str, user_id: str) -> int:
        """Delete Chroma rows for one document (user-scoped)."""
        return await self.vector_store.delete_where({"user_id": user_id, "doc_id": doc_id})

    async def delete_catalog_document(self, doc_id: str, user_id: str) -> dict[str, Any] | None:
        """Remove one indexed file: its vectors, catalog row, and original bytes."""
        existing = await self.documents.get_document(doc_id, user_id)
        if existing is None:
            return None
        source_id = str(existing.get("source_id") or "")
        embeddings = 0
        if source_id:
            embeddings = await self.delete_document_embeddings(source_id, user_id)
        triples_path = str(existing.get("triples_path") or "")
        removed = await self.documents.delete_document(doc_id, user_id)
        _remove_triples_file(triples_path, user_id)
        return {
            "deleted": removed,
            "embeddings": embeddings,
            "source_id": source_id,
        }

    async def delete_user_memory(self, user_id: str) -> dict[str, int]:
        """Drop every vector and raw document that belongs to this user."""
        embeddings = await self.vector_store.delete_where({"user_id": user_id})
        documents = await self.documents.delete_all_for_user(user_id)
        return {"documents": documents, "embeddings": embeddings}


rag_service = RAGService()
