"""Documents router — JWT-scoped memory catalog.

Processing: the upload is still in the queue.
Distilled: facts were extracted, and the vectors are not stored yet.
Embedded: the vectors are in memory, so Brain can recall the file.

Distilled does not mean the file is queued for fine-tuning.
"""

from pathlib import Path
from typing import Annotated

import httpx
from auth import require_premium
from config import get_settings
from db import delete_owned_task, list_user_tasks
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from logging_setup import log_with_correlation

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents")
async def list_documents(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
    kind: str | None = Query(default=None),
):
    """List the caller's memory, with a count for each file kind."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/documents")
    return await _catalog(request, user, kind=kind, query="")


@router.get("/documents/search")
async def search_documents(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
    q: str = Query(default=""),
    kind: str | None = Query(default=None),
):
    """Search the caller's files by name and extracted summary."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/documents/search")
    return await _catalog(request, user, kind=kind, query=q)


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_document(
    request: Request,
    doc_id: str,
    user: Annotated[dict, Depends(require_premium)],
):
    """Remove one memory file. A queued upload is removed even before embedding."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    user_id = user["user_id"]
    log_with_correlation(correlation_id, "info", f"DELETE /api/documents/{doc_id}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{settings.RAG_SERVICE_URL}/documents/{doc_id}",
                params={"user_id": user_id},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory could not be deleted.",
        ) from exc
    if response.status_code == status.HTTP_200_OK:
        source_id = str((response.json() or {}).get("source_id") or "")
        if source_id:
            await delete_owned_task(source_id, user_id)
        _remove_local_triples(user_id, source_id or doc_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if response.status_code != status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Memory could not be deleted.",
        )
    removed = await delete_owned_task(doc_id, user_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _remove_local_triples(user_id: str, correlation_id: str) -> None:
    if not correlation_id or "/" in correlation_id or correlation_id in {".", ".."}:
        return
    path = Path("/app/data/triples") / user_id / f"{correlation_id}.jsonl"
    path.unlink(missing_ok=True)


@router.get("/documents/{doc_id}")
async def get_document(
    request: Request,
    doc_id: str,
    user: Annotated[dict, Depends(require_premium)],
):
    """Fetch one document owned by the caller. Otherwise 404."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    log_with_correlation(correlation_id, "info", f"GET /api/documents/{doc_id}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.RAG_SERVICE_URL}/documents/{doc_id}",
                params={"user_id": user["user_id"]},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RAG service error: {exc}",
        ) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="RAG service error",
        )
    return response.json()


async def _catalog(request: Request, user: dict, *, kind: str | None, query: str) -> dict:
    correlation_id = request.state.correlation_id
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.RAG_SERVICE_URL}/documents",
                params={"user_id": user["user_id"]},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RAG service error: {exc}",
        ) from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="RAG service error",
        )
    stored = response.json().get("documents") or []
    rows = [_view_document(doc) for doc in stored]
    rows = [row for row in rows if row is not None]
    known = {row["id"] for row in rows}
    known.update(row["source_id"] for row in rows if row.get("source_id"))
    for task in await list_user_tasks(user["user_id"]):
        if task.get("_id") in known:
            continue
        viewed = _view_task(task)
        if viewed is not None:
            rows.append(viewed)
    counts = {
        "document": sum(1 for row in rows if row["kind"] == "document"),
        "image": sum(1 for row in rows if row["kind"] == "image"),
        "video": sum(1 for row in rows if row["kind"] == "video"),
    }
    needle = " ".join(query.split()).lower()
    visible = rows
    if needle:
        visible = [
            row
            for row in visible
            if needle in row["name"].lower() or needle in row["summary"].lower()
        ]
    if kind in {"document", "image", "video"}:
        visible = [row for row in visible if row["kind"] == kind]
    for row in visible:
        row.pop("source_id", None)
    return {"documents": visible, "total": len(visible), "counts": counts}


def _view_document(doc: dict) -> dict | None:
    kind = _kind(str(doc.get("content_type") or ""), str(doc.get("type") or ""))
    if kind is None:
        return None
    added = doc.get("created_at")
    if hasattr(added, "isoformat"):
        added = added.isoformat()
    return {
        "id": str(doc.get("_id") or ""),
        "source_id": str(doc.get("source_id") or ""),
        "name": (doc.get("filename") or "").strip() or "Untitled",
        "kind": kind,
        "content_type": str(doc.get("content_type") or ""),
        "added": added or "",
        "status": "Embedded",
        "summary": (doc.get("summary") or "").strip(),
    }


def _view_task(task: dict) -> dict | None:
    kind = _kind(str(task.get("content_type") or ""), "")
    if kind is None:
        return None
    state = task.get("status")
    if state == "in_progress":
        label = "Processing"
        summary = ""
    elif state == "success":
        label = "Distilled"
        result = task.get("result") or {}
        summary = (result.get("summary") or "").strip() if isinstance(result, dict) else ""
    else:
        return None
    added = task.get("created_at")
    if hasattr(added, "isoformat"):
        added = added.isoformat()
    return {
        "id": str(task.get("_id") or ""),
        "name": (task.get("filename") or "").strip() or "Untitled",
        "kind": kind,
        "content_type": str(task.get("content_type") or ""),
        "added": added or "",
        "status": label,
        "summary": summary,
    }


def _kind(content_type: str, modality: str) -> str | None:
    value = (content_type or modality or "").lower()
    if value.startswith("audio/") or value == "audio":
        return None
    if value.startswith("image/") or value == "image":
        return "image"
    if value.startswith("video/") or value == "video":
        return "video"
    return "document"
