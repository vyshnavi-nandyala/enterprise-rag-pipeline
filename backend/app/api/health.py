import time

import anthropic
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.database import get_db
from app.models.schemas import HealthResponse, HealthStatus

router = APIRouter(prefix="/health", tags=["health"])
_settings = get_settings()


@router.get("/db", response_model=HealthStatus)
async def health_db(db: AsyncSession = Depends(get_db)) -> HealthStatus:
    try:
        t0 = time.perf_counter()
        await db.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - t0) * 1000
        return HealthStatus(status="healthy", latency_ms=round(latency_ms, 2))
    except Exception as exc:
        return HealthStatus(status="unhealthy", detail=str(exc))


@router.get("/llm", response_model=HealthStatus)
async def health_llm() -> HealthStatus:
    try:
        t0 = time.perf_counter()
        client = anthropic.AsyncAnthropic(api_key=_settings.anthropic_api_key)
        msg = await client.messages.create(
            model=_settings.claude_model,
            max_tokens=5,
            messages=[{"role": "user", "content": "ping"}],
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        return HealthStatus(
            status="healthy",
            latency_ms=round(latency_ms, 2),
            detail=f"model={_settings.claude_model}",
        )
    except Exception as exc:
        return HealthStatus(status="unhealthy", detail=str(exc))


@router.get("/", response_model=HealthResponse)
async def health_all(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    db_status = await health_db(db)
    return HealthResponse(db=db_status)
