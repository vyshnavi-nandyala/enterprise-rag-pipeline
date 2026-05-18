from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_audit_logger, get_logger
from app.core.security import detect_prompt_injection, redact_pii, verify_api_key
from app.models.database import get_db
from app.models.schemas import ChatQueryRequest, ChatQueryResponse
from app.services.rag_engine import RAGEngine

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
_logger = get_logger(__name__)
_rag_engine = RAGEngine()


@router.post("/query", response_model=ChatQueryResponse, dependencies=[Depends(verify_api_key)])
async def query(
    request: Request,
    body: ChatQueryRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatQueryResponse:
    ip = request.client.host if request.client else None
    audit = get_audit_logger()

    pii_result = redact_pii(body.query)
    injection_detected = detect_prompt_injection(pii_result.redacted_text)

    audit.log(
        "chat_query",
        user_id=body.user_id,
        ip=ip,
        pii_detected=pii_result.pii_detected,
        injection_detected=injection_detected,
    )

    if pii_result.pii_detected:
        _logger.warning("pii_detected_in_query", extra={"patterns": pii_result.patterns_found, "ip": ip})

    if injection_detected:
        _logger.warning("prompt_injection_detected", extra={"ip": ip, "user_id": body.user_id})

    return await _rag_engine.query(
        query=pii_result.redacted_text,
        db=db,
        user_id=body.user_id,
        ip_address=ip,
        department_filter=body.department_filter,
        flagged_for_injection=injection_detected,
        pii_detected=pii_result.pii_detected,
    )
