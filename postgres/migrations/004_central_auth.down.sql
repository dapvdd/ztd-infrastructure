-- Sprint 5 — 004_central_auth rollback.
-- Drops ONLY objects created by 004_central_auth.up.sql.
-- Legacy tables (devices, telemetry, deployment_logs, provisioning_*) are
-- untouched. Application-level rollback: revert to the aa8622c image and the
-- pre-sprint nginx/BFF auth; the dropped tables carried no legacy data.

BEGIN;

DROP INDEX IF EXISTS idx_app_audit_events_action;
DROP INDEX IF EXISTS idx_app_audit_events_actor;
DROP INDEX IF EXISTS idx_app_audit_events_created_at;
DROP TABLE IF EXISTS app_audit_events;

DROP INDEX IF EXISTS idx_app_sessions_active;
DROP INDEX IF EXISTS idx_app_sessions_expires_at;
DROP INDEX IF EXISTS idx_app_sessions_user_id;
DROP TABLE IF EXISTS app_sessions;

DROP TABLE IF EXISTS app_users;

COMMIT;
