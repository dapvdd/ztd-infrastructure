-- Enable pgcrypto for UUID generation (gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Table 1: Device Inventory & Whitelist
CREATE TABLE IF NOT EXISTS devices (
    id VARCHAR(32) PRIMARY KEY,          -- diisi device_id (raspi-xxxxxx)
    room_id VARCHAR(50),                 -- ruangan tempat Pi berada
    hostname VARCHAR(100),
    ip_address VARCHAR(45),              -- IP Tailscale
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE
);

-- Table 2: Deployment Audit Logs
CREATE TABLE IF NOT EXISTS deployment_logs (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(32) REFERENCES devices(id) ON DELETE CASCADE,
    stage VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    log_output TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: Telemetry Store
CREATE TABLE IF NOT EXISTS telemetry (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(32) REFERENCES devices(id) ON DELETE CASCADE,
    cpu_temp NUMERIC(5, 2),              -- raw value, unit is in temp_unit
    temp_unit VARCHAR(1),                -- 'C' | 'F' | NULL (legacy, never inferred)
    schema_version SMALLINT,             -- publisher contract version (2 = explicit unit)
    ram_usage NUMERIC(5, 2),
    uptime_seconds BIGINT,
    payload JSONB,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
