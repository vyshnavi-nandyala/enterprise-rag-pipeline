# Enterprise HR Policy RAG Pipeline

A production-grade Retrieval-Augmented Generation (RAG) system that lets employees ask natural-language questions about HR policies and receive grounded answers with source citations — powered by **Claude Sonnet**, **OpenAI embeddings**, and **PostgreSQL + pgvector**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React + Vite Chat UI  (dark theme, citation expansion) │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP (X-API-Key auth)
┌────────────────────────▼────────────────────────────────┐
│  FastAPI Backend                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  /chat/query │  │/ingest/upload│  │  /health/*    │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘  │
│         │                 │                              │
│  ┌──────▼───────┐  ┌──────▼───────┐                      │
│  │  RAG Engine  │  │  Ingestion   │                      │
│  │  - PII check │  │  - PDF/DOCX/ │                      │
│  │  - Injection │  │    TXT parse │                      │
│  │    defense   │  │  - Chunking  │                      │
│  │  - HNSW      │  │  - Embed     │                      │
│  │    search    │  └──────────────┘                      │
│  │  - Claude    │                                        │
│  │    Sonnet    │                                        │
│  └──────────────┘                                        │
└────────────────────────────────────────────────────────-┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  PostgreSQL 16 + pgvector                                │
│  documents | document_chunks (HNSW) | query_logs         │
└─────────────────────────────────────────────────────────┘
```

## Features

| Feature | Details |
|---------|---------|
| **Document ingestion** | PDF, DOCX, TXT · recursive chunking (512 tok / 64 overlap) · OpenAI `text-embedding-3-small` |
| **RAG pipeline** | HNSW vector search · top-K retrieval · Claude Sonnet answer with `[Source N]` citations |
| **Security** | PII redaction (SSN, email, phone) · prompt injection detection · API key auth · JSONL audit log |
| **Observability** | Token cost per query · p95 latency SLO monitoring (retrieval < 3s, e2e < 8s) · structured JSON logs |
| **Frontend** | Dark-theme React chat UI · expandable citations · telemetry display · document upload |
| **Infra** | Docker Compose · Terraform (AWS ECS Fargate + RDS + Secrets Manager + ECR) |
| **CI/CD** | GitHub Actions: lint → test → build → push to GHCR |

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Anthropic API key
- OpenAI API key

```bash
# 1. Clone and configure
git clone https://github.com/vyshnavi-nandyala/enterprise-rag-pipeline.git
cd enterprise-rag-pipeline
cp .env.example .env
# Edit .env: fill ANTHROPIC_API_KEY, OPENAI_API_KEY, API_KEY, POSTGRES_PASSWORD

# 2. Start
docker compose up --build -d

# 3. Verify
curl http://localhost:8000/health/db
# {"status":"healthy","latency_ms":1.23}

# 4. Open the chat UI
open http://localhost:3000
```

### Upload a Policy Document

```bash
curl -X POST http://localhost:8000/api/v1/ingest/upload \
  -H "X-API-Key: $API_KEY" \
  -F "file=@hr-vacation-policy.pdf" \
  -F "department=Engineering"
```

### Ask a Question

```bash
curl -X POST http://localhost:8000/api/v1/chat/query \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "How many vacation days do I accrue per year?"}'
```

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/chat/query` | `X-API-Key` | RAG query with citations |
| `POST` | `/api/v1/ingest/upload` | `X-API-Key` | Upload PDF/DOCX/TXT |
| `GET` | `/api/v1/ingest/documents` | `X-API-Key` | List ingested documents |
| `GET` | `/health/db` | None | Database health check |
| `GET` | `/health/llm` | None | LLM connectivity check |
| `GET` | `/docs` | None | Swagger UI |

### Chat Query Response

```json
{
  "query_id": "3f8a1b2c-...",
  "answer": "Full-time employees accrue 15 vacation days per year [Source 1]...",
  "sources": [
    {
      "source_id": 1,
      "filename": "hr-vacation-policy.pdf",
      "department": "All",
      "chunk_index": 3,
      "excerpt": "Full-time employees accrue 1.25 days per month...",
      "similarity_score": 0.9231
    }
  ],
  "retrieval_latency_ms": 12.4,
  "total_latency_ms": 1843.2,
  "token_cost_usd": 0.000423,
  "prompt_tokens": 892,
  "completion_tokens": 214,
  "flagged_for_injection": false,
  "pii_detected": false
}
```

## Project Structure

```
enterprise-rag-pipeline/
├── backend/
│   ├── app/
│   │   ├── api/          # chat.py, ingest.py, health.py
│   │   ├── core/         # config.py, logging.py, security.py
│   │   ├── services/     # rag_engine.py, ingestion.py
│   │   ├── models/       # database.py, schemas.py
│   │   └── main.py
│   ├── tests/            # test_security.py, test_chunking.py
│   └── requirements.txt
├── frontend/
│   └── src/              # App.tsx, index.css, main.tsx
├── infra/
│   ├── docker/           # Dockerfile.backend, Dockerfile.frontend, init.sql
│   └── terraform/        # main.tf (ECS + RDS + ECR + Secrets Manager)
├── docs/
│   ├── architecture-decisions.md
│   └── runbook.md
├── .github/workflows/    # ci.yml
├── docker-compose.yml
├── .env.example
└── README.md
```

## Development

### Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

### Backend Only (without Docker)

```bash
cd backend
pip install -r requirements.txt
# Requires local PostgreSQL with pgvector; see infra/docker/init.sql
uvicorn app.main:app --reload
```

### Frontend Only

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

## Infrastructure (AWS)

See `infra/terraform/main.tf` for the full Terraform configuration:

- **ECS Fargate** — backend (2 tasks, 1 vCPU, 2 GB) + frontend (nginx)
- **RDS PostgreSQL 16** — db.t3.medium, Multi-AZ, encrypted, 7-day backups
- **ECR** — container registries for backend + frontend
- **Secrets Manager** — API keys injected at task startup (never in env vars directly)
- **CloudWatch** — structured logs with 30-day retention

```bash
cd infra/terraform
terraform init && terraform apply
```

## Security

- **PII redaction** — SSN, email, phone patterns stripped before query processing and logging
- **Prompt injection defense** — 11 regex patterns covering common jailbreak attempts
- **API key auth** — `X-API-Key` header required on all data endpoints
- **Audit log** — every query logged to JSONL with user ID, IP, PII/injection flags
- **Non-root containers** — Dockerfiles create and run as `app` system user
- **Secrets Manager** — credentials never baked into images or committed to git

## Architecture Decision Records

- [ADR-001: pgvector vs Pinecone](docs/architecture-decisions.md#adr-001)
- [ADR-002: Claude Sonnet vs GPT-4o](docs/architecture-decisions.md#adr-002)
- [ADR-003: Chunking Strategy](docs/architecture-decisions.md#adr-003)
- [ADR-004: API Key Authentication](docs/architecture-decisions.md#adr-004)

## Runbook

See [docs/runbook.md](docs/runbook.md) for:
- Production deployment steps
- Incident response playbooks (latency, LLM errors, injection attempts)
- Database maintenance (VACUUM, index rebuild, log archival)
- SLO monitoring queries
- Scaling guide

## License

MIT
