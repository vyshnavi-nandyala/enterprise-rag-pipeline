from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import verify_api_key
from app.models.database import Document, get_db
from app.models.schemas import DocumentResponse, IngestResponse
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
_logger = get_logger(__name__)
_ingestion_service = IngestionService()

ALLOWED_TYPES = {"pdf", "docx", "txt"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", response_model=IngestResponse, dependencies=[Depends(verify_api_key)])
async def upload_document(
    file: UploadFile = File(...),
    department: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{ext}' is not supported. Allowed: {', '.join(ALLOWED_TYPES)}",
        )

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)} MB",
        )

    _logger.info("ingest_upload_received", extra={"filename": file.filename, "size": len(data)})

    try:
        doc = await _ingestion_service.ingest(
            data=data,
            filename=file.filename,
            department=department,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return IngestResponse(
        document_id=doc.id,
        filename=doc.filename,
        total_chunks=doc.total_chunks,
        message="Document ingested successfully",
    )


@router.get("/documents", response_model=list[DocumentResponse], dependencies=[Depends(verify_api_key)])
async def list_documents(
    department: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    stmt = select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
    if department:
        stmt = stmt.where(Document.department == department)
    result = await db.execute(stmt)
    docs = result.scalars().all()
    return [DocumentResponse.model_validate(d) for d in docs]
