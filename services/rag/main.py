"""RAG Service — Standalone Microservice.

Provides semantic search, document chunking, and context injection.
Runs on Port 8002 as an independent FastAPI service.
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel

from config import settings

# --- Structured Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("rag-service")


class CorrelationFilter(logging.Filter):
    """Add correlation_id to all log records."""

    def filter(self, record):
        record.correlation_id = getattr(record, "correlation_id", "no-id")
        return True


logger.addFilter(CorrelationFilter())


def log_with_correlation(correlation_id: str, level: str, message: str):
    """Log a message with correlation_id context."""
    extra = {"correlation_id": correlation_id}
    getattr(logger, level)(message, extra=extra)


app = FastAPI(
    title="RAG Service",
    description="Hybrid Store + RAG — Semantic search and context injection",
    version="0.1.0",
)


# --- Health endpoint ---
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "rag-service",
        "version": "0.1.0",
    }


# --- Request/Response models ---
class SearchRequest(BaseModel):
    """Search request schema."""

    query: str
    user_id: str
    k: int = 3


class SearchResponse(BaseModel):
    """Search response schema."""

    results: list[dict]
    total: int


class ContextResponse(BaseModel):
    """Context injection response schema."""

    context: str
    sources: list[str]


class IngestRequest(BaseModel):
    """Ingest triples request schema."""

    user_id: str
    doc_id: str
    triples_path: str


class IngestResponse(BaseModel):
    """Ingest response schema."""

    triples_count: int
    status: str


# --- Endpoints ---
@app.get("/search", response_model=SearchResponse)
async def semantic_search(
    request: Request,
    query: str = Query(..., description="Search query"),
    user_id: str = Query(..., description="User ID for isolation"),
    k: int = Query(3, description="Number of results"),
):
    """Semantic search for relevant documents."""
    from services.rag.rag_service import rag_service

    correlation_id = getattr(request.state, "correlation_id", "no-id")
    log_with_correlation(correlation_id, "info", f"Semantic search: query='{query[:50]}...' user={user_id}")

    try:
        results = await rag_service.semantic_search(query, user_id, k)
        log_with_correlation(correlation_id, "info", f"Search returned {len(results)} results")
        return SearchResponse(results=results, total=len(results))
    except Exception as e:
        log_with_correlation(correlation_id, "error", f"Search failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}",
        )


@app.get("/context", response_model=ContextResponse)
async def get_context(
    request: Request,
    query: str = Query(..., description="User question"),
    user_id: str = Query(..., description="User ID for isolation"),
):
    """Get context for LLM injection."""
    from services.rag.rag_service import rag_service

    correlation_id = getattr(request.state, "correlation_id", "no-id")
    log_with_correlation(correlation_id, "info", f"Context injection: query='{query[:50]}...' user={user_id}")

    try:
        context = await rag_service.context_injection(query, user_id)

        # Extract sources from context
        sources = []
        if context and context != "No relevant context found in your documents.":
            sources = [
                line.split("(source: ")[-1].rstrip(")")
                for line in context.split("\n")
                if "(source:" in line
            ]

        log_with_correlation(correlation_id, "info", f"Context returned: {len(sources)} sources")
        return ContextResponse(context=context, sources=sources)
    except Exception as e:
        log_with_correlation(correlation_id, "error", f"Context injection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context error: {str(e)}",
        )


@app.post("/ingest", response_model=IngestResponse)
async def ingest_triples(request: Request, ingest_request: IngestRequest):
    """Ingest JSONL triples into vector store."""
    from services.rag.rag_service import rag_service

    correlation_id = getattr(request.state, "correlation_id", "no-id")
    log_with_correlation(
        correlation_id, "info",
        f"Ingesting triples: user={ingest_request.user_id} doc={ingest_request.doc_id}"
    )

    try:
        count = await rag_service.ingest_triples(
            user_id=ingest_request.user_id,
            doc_id=ingest_request.doc_id,
            triples_path=ingest_request.triples_path,
        )
        log_with_correlation(correlation_id, "info", f"Ingested {count} triples")
        return IngestResponse(
            triples_count=count,
            status="success" if count > 0 else "no triples found",
        )
    except Exception as e:
        log_with_correlation(correlation_id, "error", f"Ingest failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingest error: {str(e)}",
        )


@app.delete("/embeddings/{doc_id}")
async def delete_embeddings(
    request: Request,
    doc_id: str,
    user_id: str = Query(..., description="User ID for isolation"),
):
    """Delete all embeddings for a document."""
    from services.rag.rag_service import rag_service

    correlation_id = getattr(request.state, "correlation_id", "no-id")
    log_with_correlation(correlation_id, "info", f"Deleting embeddings: doc={doc_id} user={user_id}")

    try:
        await rag_service.delete_document_embeddings(doc_id, user_id)
        log_with_correlation(correlation_id, "info", f"Deleted embeddings for doc {doc_id}")
        return {"status": "deleted", "doc_id": doc_id}
    except Exception as e:
        log_with_correlation(correlation_id, "error", f"Delete failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete error: {str(e)}",
        )
