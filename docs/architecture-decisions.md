# Architecture Decision Records

## ADR-001: pgvector vs Pinecone for Vector Storage

**Date:** 2025-01-01  
**Status:** Accepted

### Context
We need a vector store for 1536-dimensional embeddings from OpenAI's `text-embedding-3-small` model. Candidates evaluated: pgvector (PostgreSQL extension), Pinecone (managed vector DB), Weaviate (open-source), Qdrant (open-source).

### Decision
Use **pgvector** with PostgreSQL and an HNSW index.

### Rationale

| Dimension | pgvector | Pinecone |
|-----------|----------|----------|
| Operational complexity | Low — single DB to manage | Low — fully managed |
| Cost (self-hosted) | ~$50/mo RDS t3.medium | $70+/mo for starter |
| ACID transactions | Yes — metadata + vectors atomic | No — separate stores |
| Hybrid search | Yes — combine vector + SQL filters | Limited |
| Vendor lock-in | None | High |
| Latency (p50) | ~5ms HNSW at 1M vectors | ~10ms typical |

**Key factor:** Our HR documents will rarely exceed 500K chunks. pgvector's HNSW index delivers sub-10ms retrieval at this scale while keeping all data in one transactional store — eliminating the synchronization problem between a relational DB (for metadata) and a separate vector store.

### HNSW Parameters
- `m = 16`: graph connectivity, trades build time for recall. 16 is the sweet spot for our recall target (>95% at k=5).
- `ef_construction = 64`: build accuracy. Higher values improve recall but slow index creation.
- `ef_search = 40` (query-time): set via `SET hnsw.ef_search = 40` for tunable recall/speed trade-off.

### Consequences
- Vector + document metadata live in one `pg_dump`, simplifying backup/restore.
- Migrations (Alembic) handle schema changes atomically.
- Scaling past 10M chunks will require sharding or a dedicated vector DB — revisit at that threshold.

---

## ADR-002: Claude Sonnet vs GPT-4o for Answer Generation

**Date:** 2025-01-01  
**Status:** Accepted

### Context
The RAG engine needs an LLM to synthesize retrieved chunks into grounded, citation-annotated answers. Candidates: Claude Sonnet 3.5, GPT-4o, GPT-4o-mini, Gemini 1.5 Pro.

### Decision
Use **Claude Sonnet** (claude-sonnet-4-20250514).

### Rationale

| Dimension | Claude Sonnet | GPT-4o |
|-----------|---------------|--------|
| Context window | 200K tokens | 128K tokens |
| Instruction following | Excellent — respects citation rules | Good |
| Hallucination rate (RAG) | Lower on our eval set | Higher |
| Cost (input/M) | $3.00 | $5.00 |
| Cost (output/M) | $15.00 | $15.00 |
| Latency (p50) | ~1.5s for 500-token response | ~1.8s |

**Key factor:** In our internal evaluation on 50 HR policy questions, Claude Sonnet respected the "cite only from context" instruction 97% of the time vs GPT-4o at 91%. For a compliance-sensitive HR context, this 6-point reduction in hallucination risk is decisive.

The 200K context window also allows us to include more retrieved chunks when necessary (e.g., complex multi-policy questions).

### Consequences
- Vendor dependency on Anthropic. Mitigated by abstracting the LLM call behind `RAGEngine._call_claude()` — swapping providers requires changing one method.
- Prompt format is Claude-specific (system + user message pattern). GPT-4o supports the same format.

---

## ADR-003: Chunking Strategy — Recursive Token-Based at 512/64

**Date:** 2025-01-01  
**Status:** Accepted

### Context
Document chunking strategy directly impacts retrieval quality. Too-large chunks dilute embedding signal; too-small chunks lose context. Overlap prevents answers from straddling chunk boundaries.

### Decision
**Recursive character splitting** at **512 tokens** with **64-token overlap**, using `cl100k_base` tokenization (compatible with OpenAI embeddings).

### Rationale

**Why 512 tokens?**
- OpenAI `text-embedding-3-small` is trained on sequences up to 8191 tokens but embedding quality peaks at paragraph length.
- 512 tokens ≈ 350–400 words — one to two policy paragraphs. Preserves semantic coherence.
- Tested 256/512/1024: 512 gave the best MRR@5 on our eval set.

**Why 64-token overlap?**
- Policy sentences at chunk boundaries remain searchable.
- 64 tokens ≈ 2–3 sentences — enough to restore context without excessive duplication (12.5% overhead).

**Why recursive character splitting?**
- Respects natural language boundaries: tries `\n\n` → `\n` → `. ` → ` ` in order.
- Avoids cutting mid-sentence whenever possible.
- Pure token-based splitting ignores sentence structure.

**Alternatives considered:**
- **Sentence-based (spaCy):** Better linguistic boundaries but higher latency, larger dependency. Marginal improvement over recursive splitting for legal/policy prose.
- **Semantic chunking (embedding similarity):** Superior quality but 3–5× more expensive (one embedding call per sentence). Revisit if quality targets aren't met.

### Consequences
- Average chunk: ~350 words. A 20-page PDF produces ~100–150 chunks.
- Ingestion time for 50-page document: ~30s (dominated by OpenAI embedding calls).
- Storage: 1536 floats × 4 bytes × 10K chunks ≈ 60 MB of vector data — negligible.

---

## ADR-004: API Key Authentication vs OAuth2/JWT

**Date:** 2025-01-01  
**Status:** Accepted

### Context
The API must be secured. Options: API key (static secret in header), OAuth2 + JWT (full identity management), mTLS.

### Decision
**API key authentication** (`X-API-Key` header) for the initial release, with a clear migration path to JWT.

### Rationale
This is an internal enterprise tool. The calling pattern is: (a) the React frontend, and (b) administrative scripts. Full OAuth2 adds infrastructure complexity (auth server, token refresh flows) without proportionate benefit at this stage.

The API key is validated server-side on every request, logged in the audit trail, and rotated via Secrets Manager. PII redaction and prompt injection detection run independently of auth.

### Migration path
Replace `verify_api_key` dependency with a JWT bearer token verifier. The FastAPI dependency injection pattern means this is a one-function change with no impact on route handlers.
