CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    key_id TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'ai.read',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id
    ON api_keys (user_id);
