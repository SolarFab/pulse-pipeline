-- preference-feed 1.1: pgvector + event embeddings.
-- Dimension 1536 = openai/text-embedding-3-small, decided by Experiment 1
-- (hand-labeled qrels: R@5 0.776 / MRR 0.78 / nDCG@5 0.716 — see docs/embedding-benchmark-qrels.md).

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE events ADD COLUMN IF NOT EXISTS embedding   vector(1536);
ALTER TABLE events ADD COLUMN IF NOT EXISTS embed_model TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS embed_hash  TEXT;   -- sha256 of build_embed_text(); skip re-embeds

-- HNSW cosine index; NULL embeddings (not yet embedded / degraded ingest) are simply absent from it.
CREATE INDEX IF NOT EXISTS events_embedding_hnsw
    ON events USING hnsw (embedding vector_cosine_ops);
