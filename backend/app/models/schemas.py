from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    source_id: int
    filename: str
    department: Optional[str] = None
    chunk_index: int
    excerpt: str
    similarity_score: float


class ChatQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Employee question")
    user_id: Optional[str] = Field(None, max_length=100)
    department_filter: Optional[str] = Field(None, max_length=100)


class ChatQueryResponse(BaseModel):
    query_id: str
    answer: str
    sources: list[SourceCitation]
    retrieval_latency_ms: float
    total_latency_ms: float
    token_cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    flagged_for_injection: bool
    pii_detected: bool


class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_hash: str
    version: int
    department: Optional[str]
    file_type: str
    total_chunks: int
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    total_chunks: int
    message: str


class HealthStatus(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    db: HealthStatus
    llm: Optional[HealthStatus] = None
