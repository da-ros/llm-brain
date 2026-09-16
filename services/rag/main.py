"""RAG Service — Hybrid Store + RAG microservice on port 8002.

Local MongoDB/GridFS + Chroma (2048-dim, Qwen3-VL-Embedding-2B) with
LangChain chunking, Fernet, and per-user isolation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from config import get_settings
from document_store import document_store
from fastapi import FastAPI, HTTPException, Query, Request, status
from logging_setup import correlation_id_var, log_with_correlation, logger
from pydantic import BaseModel, Field
from rag_service import rag_service


class SearchResponse(BaseModel):
    results: list[dict] = Field(default_factory=list)
    total: int = 0


class ContextResponse(BaseModel):
    context: str
    sources: list[str] = Field(default_factory=list)


class IngestRequest(BaseModel):
    user_id: str
    doc_id: str
    triples_path: str
    gridfs_id: str = ""
    doc_type: str = "text"


class IngestResponse(BaseModel):
    triples_count: int
    status: str


async def add_correlation_id(request: Request, call_next):
    """Propagate X-Request-ID. Do not mint a new UUID (API Router owns that)."""
    correlation_id = request.headers.get("X-Request-ID", "no-id")
    request.state.correlation_id = correlation_id
    token = correlation_id_var.set(correlation_id)
    log_with_correlation(correlation_id, "info", f"{request.method} {request.url.path}")
    try:
        response = await call_next(request)
    finally:
        correlation_id_var.reset(token)
    response.headers["X-Request-ID"] = correlation_id
    return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await document_store.connect()
    except Exception:
        logger.exception("MongoDB connection failed at startup (health still 200)")
    yield
    await document_store.close()


def create_app() -> FastAPI:
    """Build the FastAPI application (used by tests and uvicorn)."""
    settings = get_settings()
    application = FastAPI(
        title="RAG Service",
        description="Hybrid Store + RAG — local MongoDB/GridFS + Chroma + LangChain",
        version=settings.SERVICE_VERSION,
        lifespan=lifespan,
    )
    application.middleware("http")(add_correlation_id)

    @application.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
        }

    @application.get("/search", response_model=SearchResponse)
    async def semantic_search(
        request: Request,
        query: str = Query(..., description="Search query"),
        user_id: str = Query(..., description="User ID for isolation"),
        k: int = Query(3, description="Top-k"),
    ):
        correlation_id = getattr(request.state, "correlation_id", "no-id")
        log_with_correlation(
            correlation_id,
            "info",
            f"Semantic search: query='{query[:50]}' user={user_id}",
        )
        try:
            results = await rag_service.semantic_search(
                query, user_id, k, correlation_id=correlation_id
            )
            log_with_correlation(correlation_id, "info", f"Search returned {len(results)} results")
            return SearchResponse(results=results, total=len(results))
        except Exception as exc:
            log_with_correlation(correlation_id, "error", f"Search failed: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Search error: {exc}",
            ) from exc

    @application.get("/context", response_model=ContextResponse)
    async def get_context(
        request: Request,
        query: str = Query(..., description="User question"),
        user_id: str = Query(..., description="User ID for isolation"),
    ):
        correlation_id = getattr(request.state, "correlation_id", "no-id")
        log_with_correlation(
            correlation_id,
            "info",
            f"Context injection: query='{query[:50]}' user={user_id}",
        )
        try:
            context = await rag_service.context_injection(
                query, user_id, correlation_id=correlation_id
            )
            sources: list[str] = []
            if context and context != "No relevant context found in your documents.":
                sources = [
                    line.split("(source: ")[-1].rstrip(")")
                    for line in context.split("\n")
                    if "(source:" in line
                ]
            log_with_correlation(
                correlation_id, "info", f"Context returned: {len(sources)} sources"
            )
            return ContextResponse(context=context, sources=sources)
        except Exception as exc:
            log_with_correlation(correlation_id, "error", f"Context injection failed: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Context error: {exc}",
            ) from exc

    @application.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
    async def ingest_triples(request: Request, body: IngestRequest):
        correlation_id = getattr(request.state, "correlation_id", "no-id")
        log_with_correlation(
            correlation_id,
            "info",
            f"Ingesting triples: user={body.user_id} doc={body.doc_id}",
        )
        try:
            count = await rag_service.ingest_triples(
                user_id=body.user_id,
                doc_id=body.doc_id,
                triples_path=body.triples_path,
                gridfs_id=body.gridfs_id,
                doc_type=body.doc_type,
                correlation_id=correlation_id,
            )
            log_with_correlation(correlation_id, "info", f"Ingested {count} triples")
            return IngestResponse(
                triples_count=count,
                status="success" if count > 0 else "no triples found",
            )
        except Exception as exc:
            log_with_correlation(correlation_id, "error", f"Ingest failed: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Ingest error: {exc}",
            ) from exc

    @application.get("/documents")
    async def list_documents(user_id: str = Query(..., description="User ID for isolation")):
        docs = await rag_service.documents.list_documents(user_id)
        return {"documents": docs, "total": len(docs)}

    @application.get("/documents/{doc_id}")
    async def get_document(
        doc_id: str,
        user_id: str = Query(..., description="User ID for isolation"),
    ):
        doc = await rag_service.documents.get_document(doc_id, user_id)
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return doc

    @application.delete("/embeddings/{doc_id}")
    async def delete_embeddings(
        request: Request,
        doc_id: str,
        user_id: str = Query(..., description="User ID for isolation"),
    ):
        correlation_id = getattr(request.state, "correlation_id", "no-id")
        log_with_correlation(
            correlation_id, "info", f"Deleting embeddings: doc={doc_id} user={user_id}"
        )
        try:
            deleted = await rag_service.delete_document_embeddings(doc_id, user_id)
            log_with_correlation(correlation_id, "info", f"Deleted embeddings for doc {doc_id}")
            return {"status": "deleted", "doc_id": doc_id, "deleted": deleted}
        except Exception as exc:
            log_with_correlation(correlation_id, "error", f"Delete failed: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Delete error: {exc}",
            ) from exc

    return application


app = create_app()
