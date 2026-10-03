CREATE TABLE IF NOT EXISTS oidc_bindings (
    id uuid PRIMARY KEY,
    issuer text NOT NULL,
    subject text NOT NULL,
    principal text NOT NULL REFERENCES principals(token),
    linked_by text NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(issuer, subject)
);
CREATE TABLE IF NOT EXISTS oidc_sessions (
    jti uuid PRIMARY KEY,
    binding_id uuid NOT NULL REFERENCES oidc_bindings(id) ON DELETE CASCADE,
    upstream_token bytea NOT NULL,
    expires_at timestamptz NOT NULL,
    handoff_hash text UNIQUE,
    handoff_expires_at timestamptz NOT NULL
);
