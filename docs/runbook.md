# Production Runbook — Enterprise RAG Pipeline

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Deployment Steps](#deployment-steps)
3. [Environment Setup](#environment-setup)
4. [Database Maintenance](#database-maintenance)
5. [Incident Response](#incident-response)
6. [SLO Monitoring](#slo-monitoring)
7. [Scaling Guide](#scaling-guide)
8. [Security Procedures](#security-procedures)

---

## Architecture Overview

```
Users → [React Frontend (nginx)] → [FastAPI Backend]
                                        │
                            ┌───────────┼───────────┐
                            ▼           ▼           ▼
                       [PostgreSQL  [OpenAI      [Anthropic
                        +pgvector]   Embeddings]  Claude]
```

**Key components:**
- `backend/` — FastAPI async app, handles ingestion + RAG queries
- `postgres` — pgvector-enabled PostgreSQL 16, stores documents + embeddings + audit logs
- `frontend/` — React + Vite SPA served by nginx

---

## Deployment Steps

### Local (Docker Compose)

```bash
# 1. Copy and fill environment variables
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY, OPENAI_API_KEY, API_KEY, POSTGRES_PASSWORD

# 2. Start all services
docker compose up --build -d

# 3. Verify health
curl http://localhost:8000/health/db
curl http://localhost:8000/health/llm

# 4. Open UI
open http://localhost:3000
```

### AWS ECS (Production)

```bash
# Prerequisites: aws CLI configured, Terraform installed, Docker running

# 1. Initialize Terraform
cd infra/terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# 2. Build and push images (capture ECR URLs from Terraform outputs)
BACKEND_URL=$(terraform output -raw ecr_backend_url)
FRONTEND_URL=$(terraform output -raw ecr_frontend_url)

aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $BACKEND_URL

docker build -t $BACKEND_URL:latest -f infra/docker/Dockerfile.backend ./backend
docker push $BACKEND_URL:latest

docker build -t $FRONTEND_URL:latest -f infra/docker/Dockerfile.frontend ./frontend
docker push $FRONTEND_URL:latest

# 3. Force new ECS deployment
aws ecs update-service --cluster enterprise-rag-prod-cluster \
  --service enterprise-rag-prod-backend --force-new-deployment

# 4. Run DB migrations (connect via AWS Systems Manager Session Manager or bastion)
# The init.sql runs on first startup. For subsequent migrations, use Alembic:
# alembic upgrade head
```

### Rolling Deployment (zero-downtime)

ECS Fargate with `desired_count = 2` performs rolling updates by default:
1. ECS starts a new task with the updated image
2. ALB health check confirms the new task is healthy
3. ECS drains connections from the old task
4. Old task is terminated

---

## Environment Setup

### Required Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API key | Yes |
| `OPENAI_API_KEY` | OpenAI API key (embeddings) | Yes |
| `API_KEY` | X-API-Key header secret | Yes |
| `DATABASE_URL` | PostgreSQL connection URL | Yes |
| `POSTGRES_PASSWORD` | DB password (docker-compose) | Yes |
| `CLAUDE_MODEL` | Claude model ID | No (default: claude-sonnet-4-20250514) |
| `TOP_K` | Number of chunks to retrieve | No (default: 5) |
| `LOG_LEVEL` | Logging verbosity | No (default: INFO) |

### Rotating API Keys

1. Generate a new key: `openssl rand -hex 32`
2. Update in AWS Secrets Manager:
   ```bash
   aws secretsmanager update-secret \
     --secret-id enterprise-rag-prod/app-secrets \
     --secret-string '{"API_KEY":"new-key-here",...}'
   ```
3. Force new ECS deployment to pick up the new secret
4. Update the frontend's `VITE_API_KEY` env var and redeploy

---

## Database Maintenance

### Backup

RDS automated backups run daily at 03:00 UTC with 7-day retention.

Manual snapshot:
```bash
aws rds create-db-snapshot \
  --db-instance-identifier enterprise-rag-prod-postgres \
  --db-snapshot-identifier manual-$(date +%Y%m%d)
```

### VACUUM and Index Health

pgvector HNSW indexes don't need manual VACUUM, but table bloat can accumulate:
```sql
-- Check index health
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats WHERE tablename = 'document_chunks';

-- Manual VACUUM if needed (during maintenance window)
VACUUM ANALYZE document_chunks;
VACUUM ANALYZE query_logs;
```

### pgvector Index Rebuild

If retrieval quality degrades after bulk inserts:
```sql
-- Drop and rebuild HNSW index (takes ~5 min for 1M vectors)
DROP INDEX idx_chunks_embedding_hnsw;
CREATE INDEX idx_chunks_embedding_hnsw
  ON document_chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

### Purge Old Query Logs

Query logs older than 90 days can be archived:
```sql
-- Archive to a separate table, then delete
INSERT INTO query_logs_archive SELECT * FROM query_logs WHERE created_at < NOW() - INTERVAL '90 days';
DELETE FROM query_logs WHERE created_at < NOW() - INTERVAL '90 days';
```

---

## Incident Response

### INC-001: High Retrieval Latency (p95 > 3s)

**Symptoms:** `retrieval_slo_breach` warnings in logs; users report slow responses.

**Triage:**
```bash
# Check current query latency
psql $DATABASE_URL -c "
  SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY retrieval_latency_ms) AS p95
  FROM query_logs WHERE created_at > NOW() - INTERVAL '1 hour';
"

# Check index usage
psql $DATABASE_URL -c "
  SELECT * FROM pg_stat_user_indexes WHERE relname = 'document_chunks';
"
```

**Resolution:**
1. If index not being used: `SET enable_seqscan = OFF` temporarily, then investigate query plan
2. If DB CPU high: scale RDS instance class or read replica
3. If chunk count exploded: check for runaway ingestion, delete duplicate documents

---

### INC-002: LLM API Errors (Claude / OpenAI)

**Symptoms:** `POST /api/v1/chat/query` returning 500; `health/llm` unhealthy.

**Triage:**
```bash
# Check logs for API errors
docker compose logs backend | grep -i "anthropic\|openai\|rate"
```

**Resolution:**
1. **Rate limiting:** Implement exponential backoff (already in `anthropic` SDK)
2. **Invalid API key:** Rotate key per [Rotating API Keys](#rotating-api-keys)
3. **Model unavailable:** Change `CLAUDE_MODEL` env var to a fallback model and redeploy

---

### INC-003: Database Connection Exhaustion

**Symptoms:** `asyncpg: too many connections` errors in logs.

**Resolution:**
```bash
# Check active connections
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Kill idle connections
psql $DATABASE_URL -c "
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE state = 'idle' AND query_start < NOW() - INTERVAL '5 minutes';
"

# Long-term: reduce DB_POOL_SIZE in config if connection count exceeds RDS max_connections
```

---

### INC-004: Prompt Injection Attempt Detected

**Symptoms:** `prompt_injection_detected` in audit log; user receives security policy message.

**Response:**
1. Query audit log for the user's IP and user_id:
   ```sql
   SELECT * FROM query_logs WHERE flagged_for_injection = TRUE ORDER BY created_at DESC LIMIT 20;
   ```
2. If repeated attempts from same IP, add to WAF block list
3. Review injection patterns in `security.py` and add new patterns if the attempt bypassed detection

---

## SLO Monitoring

### Target SLOs

| Metric | Target | Alert threshold |
|--------|--------|----------------|
| Retrieval latency p95 | < 3,000ms | > 2,500ms |
| E2E query latency p95 | < 8,000ms | > 7,000ms |
| API availability | > 99.5% | < 99.9% |
| Ingestion success rate | > 99% | < 99.5% |

### Querying SLOs from logs

```sql
-- Last 24h latency percentiles
SELECT
  percentile_cont(0.50) WITHIN GROUP (ORDER BY retrieval_latency_ms) AS p50_retrieval,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY retrieval_latency_ms) AS p95_retrieval,
  percentile_cont(0.50) WITHIN GROUP (ORDER BY total_latency_ms) AS p50_e2e,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY total_latency_ms) AS p95_e2e,
  avg(total_cost_usd) AS avg_cost_usd,
  count(*) AS total_queries
FROM query_logs
WHERE created_at > NOW() - INTERVAL '24 hours';
```

---

## Scaling Guide

### Horizontal (ECS task count)

```bash
aws ecs update-service \
  --cluster enterprise-rag-prod-cluster \
  --service enterprise-rag-prod-backend \
  --desired-count 4
```

### Vertical (RDS instance class)

1. Modify in AWS Console or Terraform: change `db_instance_class = "db.t3.large"`
2. Apply during maintenance window to avoid downtime (or with Multi-AZ for zero-downtime)

### Adding a Read Replica (for query-heavy load)

```hcl
# Add to terraform/main.tf
resource "aws_db_instance" "postgres_replica" {
  replicate_source_db = aws_db_instance.postgres.identifier
  instance_class      = "db.t3.medium"
  ...
}
```

Then direct `/api/v1/chat/query` (read-only) to the replica connection string.

---

## Security Procedures

### PII Audit

Review the audit log for PII detections:
```bash
grep '"pii_detected": true' /var/log/rag/audit.jsonl | jq .
```

### Credential Rotation Schedule

| Credential | Rotation frequency |
|------------|-------------------|
| API_KEY | Every 90 days |
| ANTHROPIC_API_KEY | Every 180 days |
| OPENAI_API_KEY | Every 180 days |
| DB password | Every 365 days |

### Access Control Review

Monthly: verify no IAM policies grant broader access than `secretsmanager:GetSecretValue` on the specific secret ARN.
