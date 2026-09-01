"""Upload Router — File upload endpoint with ETL + RAG integration.

Handles file uploads, triggers ETL distillation, and ingests into RAG.
Premium tier only — requires valid subscription.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from services.api.main import verify_token
from services.rag.document_store import document_store
from services.rag.rag_service import rag_service

router = APIRouter(prefix="/api", tags=["upload"])

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed MIME types
ALLOWED_TYPES = {
    "application/pdf",
    "text/html",
    "message/rfc822",
    "image/png",
    "image/jpeg",
    "image/tiff",
}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    user: Annotated[dict, Depends(verify_token)],
):
    """Upload a document for processing.

    - **file**: Document to upload (PDF, HTML, EML, or image)
    - Requires valid JWT token
    - Premium tier only

    After upload:
    1. File is validated (type + size)
    2. ETL pipeline extracts triples
    3. Triples are ingested into RAG vector store
    """
    # Check premium tier
    if user.get("subscription_tier") != "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File upload requires premium subscription",
        )

    # Validate file type
    content_type = file.content_type
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: {content_type}. Allowed: {', '.join(ALLOWED_TYPES)}",
        )

    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    # Save file temporarily
    import tempfile
    from pathlib import Path

    user_id = user["user_id"]

    # Create user directory
    user_dir = Path(f"data/uploads/{user_id}")
    user_dir.mkdir(parents=True, exist_ok=True)

    file_path = user_dir / file.filename
    file_path.write_bytes(content)

    try:
        # Run ETL pipeline
        from services.etl.pipeline import distill

        triples = distill(str(file_path))
        triples_count = len(triples)

        # Store document metadata
        doc_id = await document_store.insert_document(
            user_id=user_id,
            doc_type=content_type.split("/")[-1],
            original_path=str(file_path),
            triples_path=f"data/triples/{user_id}/{file.filename}.jsonl",
        )

        # Ingest into RAG (async)
        if triples_count > 0:
            await rag_service.ingest_triples(
                user_id=user_id,
                doc_id=doc_id,
                triples_path=f"data/triples/{user_id}/{file.filename}.jsonl",
            )

        return {
            "status": "success",
            "document_id": doc_id,
            "triples_count": triples_count,
            "message": f"Document processed. {triples_count} triples extracted.",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing document: {str(e)}",
        )
