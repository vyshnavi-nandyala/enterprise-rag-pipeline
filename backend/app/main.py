import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, health, ingest
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.models.database import engine

_settings = get_settings()
setup_logging(_settings.log_level)
_logger = get_logger(__name__)

app = FastAPI(
    title="Enterprise HR Policy RAG API",
    description="AI-powered Q&A over HR policy documents using vector search and Claude Sonnet",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next) -> Response:
    t0 = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - t0) * 1000
    _logger.info(
        "http_request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": round(latency_ms, 2),
        },
    )
    return response


app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(health.router)


@app.on_event("startup")
async def startup() -> None:
    _logger.info("application_starting", extra={"model": _settings.claude_model})


@app.on_event("shutdown")
async def shutdown() -> None:
    await engine.dispose()
    _logger.info("application_shutdown")


@app.get("/", tags=["root"])
async def root() -> dict:
    return {"service": "enterprise-rag-pipeline", "version": "1.0.0", "status": "running"}
