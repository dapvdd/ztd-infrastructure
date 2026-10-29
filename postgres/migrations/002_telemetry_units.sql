-- 002_telemetry_units.sql
-- Telemetry contract v2: explicit temperature unit.
--
-- Additive and idempotent. No existing row is modified, converted, or backfilled:
-- every legacy sample keeps temp_unit = NULL and stays unlabeled.
BEGIN;

ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS temp_unit VARCHAR(1);
ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS schema_version SMALLINT;

COMMENT ON COLUMN telemetry.temp_unit IS
    'Unit of cpu_temp exactly as reported by the publisher: C or F. NULL = legacy/unlabeled sample; never inferred.';
COMMENT ON COLUMN telemetry.schema_version IS
    'Publisher contract version (2 = explicit temperature_unit). NULL = legacy payload.';

COMMIT;
