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