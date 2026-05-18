-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: lineage metadata for ingested files
CREATE TABLE IF NOT EXISTS documents (
    id          VARCHAR(36) PRIMARY KEY,
    filename    VARCHAR(255) NOT NULL,
    file_hash   VARCHAR(64) UNIQUE NOT NULL,
    version     INTEGER DEFAULT 1,
    department  VARCHAR(100),
    file_type   VARCHAR(10) NOT NULL,
    total_chunks INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Document chunks with vector embeddings
CREATE TABLE IF NOT EXISTS document_chunks (
    id           VARCHAR(36) PRIMARY KEY,
    document_id  VARCHAR(36) REFERENCES documents(id) ON DELETE CASCADE,
    content      TEXT NOT NULL,
    embedding    vector(1536),
    chunk_index  INTEGER NOT NULL,
    page_number  INTEGER,
    token_count  INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for approximate nearest-neighbor search
-- m=16 (connections per layer), ef_construction=64 (build accuracy)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text index on chunk content for hybrid search fallback
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts
    ON document_chunks
    USING gin (to_tsvector('english', content));

-- Query audit log: full trail for every RAG query
CREATE TABLE IF NOT EXISTS query_logs (
    id                    VARCHAR(36) PRIMARY KEY,
    query                 TEXT NOT NULL,
    response              TEXT,
    sources               JSONB,
    prompt_tokens         INTEGER DEFAULT 0,
    completion_tokens     INTEGER DEFAULT 0,
    total_cost_usd        FLOAT DEFAULT 0.0,
    retrieval_latency_ms  FLOAT,
    total_latency_ms      FLOAT,
    user_id               VARCHAR(100),
    ip_address            VARCHAR(45),
    flagged_for_injection BOOLEAN DEFAULT FALSE,
    pii_detected          BOOLEAN DEFAULT FALSE,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_query_logs_created_at ON query_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_logs_user_id    ON query_logs (user_id);

-- Helper function: update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
