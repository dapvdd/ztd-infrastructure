-- Sprint 5 — Centralized Authentication (fresh-install schema).
-- Mirrors postgres/migrations/004_central_auth.up.sql exactly; keep in sync.
-- Fresh installs get 01+02+03 in one init pass; existing installs apply the
-- migration instead.

BEGIN;

CREATE TABLE IF NOT EXISTS app_users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(64)  NOT NULL UNIQUE,
    password_hash   TEXT         NOT NULL,
    role            VARCHAR(16)  NOT NULL DEFAULT 'VIEWER'
                    CHECK (role IN ('ADMIN', 'VIEWER')),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS app_sessions (
    id              BIGSERIAL PRIMARY KEY,
    token_hash      CHAR(64)     NOT NULL UNIQUE,
    user_id         BIGINT       NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ  NOT NULL,
    last_seen_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,
    rotated_from    BIGINT       REFERENCES app_sessions(id) ON DELETE SET NULL,
    user_agent      VARCHAR(256)
);

CREATE INDEX IF NOT EXISTS idx_app_sessions_user_id ON app_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_app_sessions_expires_at ON app_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_app_sessions_active
    ON app_sessions(token_hash) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS app_audit_events (
    id              BIGSERIAL PRIMARY KEY,
    actor_user_id   BIGINT       REFERENCES app_users(id) ON DELETE SET NULL,
    actor_username  VARCHAR(64),
    action          VARCHAR(64)  NOT NULL,
    target_user_id  BIGINT       REFERENCES app_users(id) ON DELETE SET NULL,
    target_username VARCHAR(64),
    detail          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    source_ip       VARCHAR(64),
    user_agent      VARCHAR(256),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_audit_events_created_at ON app_audit_events(created_at);
CREATE INDEX IF NOT EXISTS idx_app_audit_events_actor ON app_audit_events(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_app_audit_events_action ON app_audit_events(action);

COMMIT;
