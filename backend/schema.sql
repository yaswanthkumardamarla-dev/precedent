CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS webhook_events (
    id          BIGSERIAL PRIMARY KEY,
    delivery_id TEXT UNIQUE NOT NULL,
    event       TEXT NOT NULL,
    action      TEXT,
    repo        TEXT,
    payload     JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS decisions (
    id                BIGSERIAL PRIMARY KEY,
    repo              TEXT NOT NULL,
    pr_number         INT NOT NULL,
    statement         TEXT NOT NULL,
    rationale         TEXT NOT NULL DEFAULT '',
    scope             TEXT NOT NULL DEFAULT '',
    source_comment_id BIGINT NOT NULL,
    source_url        TEXT NOT NULL,
    author            TEXT,
    confidence        REAL,
    status            TEXT NOT NULL DEFAULT 'proposed',
    embedding         vector(768) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS decisions_embedding_idx
    ON decisions USING hnsw (embedding vector_cosine_ops);