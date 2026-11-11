-- Destructive to provisioning-v2 data. Export these tables before an approved rollback.
-- Legacy inventory/telemetry tables are not changed by either migration.
BEGIN;
DROP TABLE provisioning_approval_events;
DROP TABLE provisioning_assignments;
DROP TABLE provisioning_modules;
DROP TABLE provisioning_devices;
COMMIT;
