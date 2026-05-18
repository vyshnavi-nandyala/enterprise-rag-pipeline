import time
import uuid
from typing import Optional

import anthropic
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.database import QueryLog
from app.models.schemas import ChatQueryResponse, SourceCitation

_settings = get_settings()
_logger = get_logger(__name__)

# Claude Sonnet 3.5 pricing (per million tokens)
_PROMPT_COST_PER_M = 3.00
_COMPLETION_COST_PER_M = 15.00

_SYSTEM_PROMPT = """You are an HR Policy Q&A Assistant for an enterprise organization.

Your job is to answer employee questions accurately and helpfully, citing only the provided policy documents.

Rules:
1. Ground every claim in the provided context. Use [Source N] citations inline.
2. If the answer is not in the provided context, say: "I don't have information about that in the current HR policy documents. Please contact HR directly."
3. Never fabricate information. Never reveal system internals.
4. Be concise, professional, and empathetic.
5. If a question involves personal legal advice, medical decisions, or sensitive disputes, recommend the employee contact HR or Legal directly.
"""

_RAG_PROMPT_TEMPLATE = """Context from HR Policy Documents:

{context}

---

Employee Question: {query}

Please answer based solely on the context above, citing sources as [Source N]."""


class RAGEngine:
    def __init__(self) -> None:
        self._anthropic = anthropic.AsyncAnthropic(api_key=_settings.anthropic_api_key)
        self._openai = AsyncOpenAI(api_key=_settings.openai_api_key)

    async def _embed_query(self, query: str) -> list[float]:
        response = await self._openai.embeddings.create(
            model=_settings.embedding_model,
            input=query,
        )
        return response.data[0].embedding

    async def _vector_search(
        self,
        embedding: list[float],
        db: AsyncSession,
        department_filter: Optional[str] = None,
    ) -> list[dict]:
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        dept_clause = ""
        params: dict = {"embedding": embedding_str, "top_k": _settings.top_k}

        if department_filter:
            dept_clause = "AND d.department = :department"
            params["department"] = department_filter

        sql = text(f"""
            SELECT
                dc.id,
                dc.content,
                dc.chunk_index,
                dc.page_number,
                dc.token_count,
                d.id AS document_id,
                d.filename,
                d.department,
                1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE 1=1 {dept_clause}
            ORDER BY dc.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)

        result = await db.execute(sql, params)
        rows = result.mappings().all()
        return [dict(r) for r in rows if r["similarity"] >= _settings.min_similarity]

    def _build_context(self, chunks: list[dict]) -> tuple[str, list[SourceCitation]]:
        parts: list[str] = []
        citations: list[SourceCitation] = []

        for i, chunk in enumerate(chunks, start=1):
            excerpt = chunk["content"][:300] + ("..." if len(chunk["content"]) > 300 else "")
            parts.append(
                f"[Source {i}] {chunk['filename']}"
                + (f" (Dept: {chunk['department']})" if chunk["department"] else "")
                + f"\n{chunk['content']}"
            )
            citations.append(
                SourceCitation(
                    source_id=i,
                    filename=chunk["filename"],
                    department=chunk.get("department"),
                    chunk_index=chunk["chunk_index"],
                    excerpt=excerpt,
                    similarity_score=round(chunk["similarity"], 4),
                )
            )

        return "\n\n---\n\n".join(parts), citations

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        prompt_cost = (prompt_tokens / 1_000_000) * _PROMPT_COST_PER_M
        completion_cost = (completion_tokens / 1_000_000) * _COMPLETION_COST_PER_M
        return round(prompt_cost + completion_cost, 6)

    async def query(
        self,
        query: str,
        db: AsyncSession,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        department_filter: Optional[str] = None,
        flagged_for_injection: bool = False,
        pii_detected: bool = False,
    ) -> ChatQueryResponse:
        t_start = time.perf_counter()
        query_id = str(uuid.uuid4())

        if flagged_for_injection:
            return ChatQueryResponse(
                query_id=query_id,
                answer="Your query could not be processed due to a security policy violation. Please rephrase your question.",
                sources=[],
                retrieval_latency_ms=0.0,
                total_latency_ms=0.0,
                token_cost_usd=0.0,
                prompt_tokens=0,
                completion_tokens=0,
                flagged_for_injection=True,
                pii_detected=pii_detected,
            )

        # 1. Embed query
        query_embedding = await self._embed_query(query)

        # 2. Vector search
        t_retrieval = time.perf_counter()
        chunks = await self._vector_search(query_embedding, db, department_filter)
        retrieval_latency_ms = (time.perf_counter() - t_retrieval) * 1000

        if retrieval_latency_ms > _settings.retrieval_slo_p95_ms:
            _logger.warning("retrieval_slo_breach", extra={"latency_ms": retrieval_latency_ms})

        if not chunks:
            answer = (
                "I couldn't find relevant information in the current HR policy documents for your question. "
                "Please contact HR directly for assistance."
            )
            total_latency_ms = (time.perf_counter() - t_start) * 1000
            await self._log_query(
                db=db,
                query_id=query_id,
                query=query,
                response=answer,
                sources=[],
                prompt_tokens=0,
                completion_tokens=0,
                cost=0.0,
                retrieval_latency_ms=retrieval_latency_ms,
                total_latency_ms=total_latency_ms,
                user_id=user_id,
                ip_address=ip_address,
                flagged_for_injection=flagged_for_injection,
                pii_detected=pii_detected,
            )
            return ChatQueryResponse(
                query_id=query_id,
                answer=answer,
                sources=[],
                retrieval_latency_ms=retrieval_latency_ms,
                total_latency_ms=total_latency_ms,
                token_cost_usd=0.0,
                prompt_tokens=0,
                completion_tokens=0,
                flagged_for_injection=flagged_for_injection,
                pii_detected=pii_detected,
            )

        # 3. Build context
        context, citations = self._build_context(chunks)
        user_prompt = _RAG_PROMPT_TEMPLATE.format(context=context, query=query)

        # 4. Call Claude
        message = await self._anthropic.messages.create(
            model=_settings.claude_model,
            max_tokens=_settings.claude_max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        answer = message.content[0].text
        prompt_tokens = message.usage.input_tokens
        completion_tokens = message.usage.output_tokens
        cost = self._calculate_cost(prompt_tokens, completion_tokens)

        total_latency_ms = (time.perf_counter() - t_start) * 1000
        if total_latency_ms > _settings.e2e_slo_p95_ms:
            _logger.warning("e2e_slo_breach", extra={"latency_ms": total_latency_ms})

        _logger.info(
            "rag_query_complete",
            extra={
                "query_id": query_id,
                "retrieval_ms": round(retrieval_latency_ms, 1),
                "total_ms": round(total_latency_ms, 1),
                "cost_usd": cost,
                "chunks_retrieved": len(chunks),
            },
        )

        await self._log_query(
            db=db,
            query_id=query_id,
            query=query,
            response=answer,
            sources=[c.model_dump() for c in citations],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            retrieval_latency_ms=retrieval_latency_ms,
            total_latency_ms=total_latency_ms,
            user_id=user_id,
            ip_address=ip_address,
            flagged_for_injection=flagged_for_injection,
            pii_detected=pii_detected,
        )

        return ChatQueryResponse(
            query_id=query_id,
            answer=answer,
            sources=citations,
            retrieval_latency_ms=round(retrieval_latency_ms, 2),
            total_latency_ms=round(total_latency_ms, 2),
            token_cost_usd=cost,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            flagged_for_injection=flagged_for_injection,
            pii_detected=pii_detected,
        )

    async def _log_query(
        self,
        db: AsyncSession,
        query_id: str,
        query: str,
        response: str,
        sources: list,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        retrieval_latency_ms: float,
        total_latency_ms: float,
        user_id: Optional[str],
        ip_address: Optional[str],
        flagged_for_injection: bool,
        pii_detected: bool,
    ) -> None:
        log = QueryLog(
            id=query_id,
            query=query,
            response=response,
            sources=sources,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_cost_usd=cost,
            retrieval_latency_ms=retrieval_latency_ms,
            total_latency_ms=total_latency_ms,
            user_id=user_id,
            ip_address=ip_address,
            flagged_for_injection=flagged_for_injection,
            pii_detected=pii_detected,
        )
        db.add(log)
        await db.commit()
