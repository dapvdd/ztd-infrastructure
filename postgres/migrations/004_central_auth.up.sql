-- Sprint 5 — Centralized Authentication: application users, revocable
-- sessions, security audit events.
--
-- Conventions: matches 001/002/003 (plain SQL, additive-only, IF NOT EXISTS,
-- ON_ERROR_STOP-friendly, idempotent). Rollback compatibility: see
-- 004_central_auth.down.sql (drops ONLY the tables/indexes created here;
-- legacy tables untouched).
--
-- Password hashes use Argon2id (argon2-cffi, PHC string format) and are
-- NEVER exported by any API endpoint.

BEGIN;

-- ---------------------------------------------------------------- users ----
CREATE TABLE IF NOT EXISTS app_users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(64)  NOT NULL UNIQUE,
    -- PHC-format Argon2id hash; never returned by any API.
    password_hash   TEXT         NOT NULL,
    role            VARCHAR(16)  NOT NULL DEFAULT 'VIEWER'
                    CHECK (role IN ('ADMIN', 'VIEWER')),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

-- ---------------------------------------------------------------- sessions --
-- Opaque bearer sessions: the cookie carries only a random 256-bit token;
-- the DB stores its SHA-256 (so a DB leak does not leak usable cookies).
CREATE TABLE IF NOT EXISTS app_sessions (
    id              BIGSERIAL PRIMARY KEY,
    token_hash      CHAR(64)     NOT NULL UNIQUE,   -- sha256 hex of the token
    user_id         BIGINT       NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ  NOT NULL,
    last_seen_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,                    -- NULL = still valid
    -- Rotation chain: when a login rotates a session (or a reset invalidates
    -- one) we record the predecessor for audit traceability.
    rotated_from    BIGINT       REFERENCES app_sessions(id) ON DELETE SET NULL,
    user_agent      VARCHAR(256)
);

CREATE INDEX IF NOT EXISTS idx_app_sessions_user_id
    ON app_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_app_sessions_expires_at
    ON app_sessions(expires_at);
-- Partial index for the hot lookup path (valid-session probe).
CREATE INDEX IF NOT EXISTS idx_app_sessions_active
    ON app_sessions(token_hash) WHERE revoked_at IS NULL;

-- --------------------------------------------------------- audit events ----
CREATE TABLE IF NOT EXISTS app_audit_events (
    id              BIGSERIAL PRIMARY KEY,
    -- NULL actor = system-initiated (e.g. automatic expiry cleanup).
    actor_user_id   BIGINT       REFERENCES app_users(id) ON DELETE SET NULL,
    actor_username  VARCHAR(64), -- snapshot: survives user deletion
    action          VARCHAR(64)  NOT NULL,
    -- LOGIN_OK, LOGIN_FAIL, LOGOUT, SESSION_REVOKED, USER_CREATED,
    -- USER_DISABLED, USER_ENABLED, ROLE_CHANGED, PASSWORD_RESET,
    -- PASSWORD_CHANGED, RATE_LIMITED, LAST_ADMIN_PROTECTION ...
    target_user_id  BIGINT       REFERENCES app_users(id) ON DELETE SET NULL,
    target_username VARCHAR(64),
    detail          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    -- Client context (no cookies/tokens ever stored here).
    source_ip       VARCHAR(64),
    user_agent      VARCHAR(256),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_audit_events_created_at
    ON app_audit_events(created_at);
CREATE INDEX IF NOT EXISTS idx_app_audit_events_actor
    ON app_audit_events(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_app_audit_events_action
    ON app_audit_events(action);

COMMIT;
