BEGIN;
CREATE TABLE provisioning_devices (
    device_id varchar(32) PRIMARY KEY CHECK (device_id ~ '^raspi-[a-z0-9-]{3,20}$'),
    credential_hash varchar(128) NOT NULL,
    created_at timestamptz NOT NULL,
    registered_at timestamptz,
    hostname varchar(100),
    approval_status varchar(20) NOT NULL DEFAULT 'PENDING'
        CHECK (approval_status IN ('PENDING','APPROVED','REJECTED','REVOKED')),
    approval_revision integer NOT NULL DEFAULT 0 CHECK (approval_revision >= 0),
    approval_expires_at timestamptz,
    configuration_revision integer NOT NULL DEFAULT 0 CHECK (configuration_revision >= 0),
    updated_at timestamptz NOT NULL,
    CHECK (hostname IS NULL OR hostname = device_id),
    CHECK (approval_status <> 'APPROVED' OR (registered_at IS NOT NULL AND approval_expires_at IS NOT NULL))
);
CREATE TABLE provisioning_modules (
    name varchar(50) PRIMARY KEY CHECK (name ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$'),
    repo_url varchar(500) NOT NULL,
    commit varchar(40) NOT NULL CHECK (commit ~ '^[0-9a-f]{40}$'),
    approved boolean NOT NULL
);
CREATE TABLE provisioning_assignments (
    device_id varchar(32) NOT NULL REFERENCES provisioning_devices(device_id),
    module_name varchar(50) NOT NULL REFERENCES provisioning_modules(name),
    repo_url varchar(500) NOT NULL,
    commit varchar(40) NOT NULL CHECK (commit ~ '^[0-9a-f]{40}$'),
    configuration json NOT NULL,
    withdrawn boolean NOT NULL DEFAULT false,
    PRIMARY KEY (device_id, module_name)
);
CREATE INDEX provisioning_assignments_module_idx ON provisioning_assignments(module_name);
CREATE TABLE provisioning_approval_events (
    device_id varchar(32) NOT NULL REFERENCES provisioning_devices(device_id),
    revision integer NOT NULL CHECK (revision > 0),
    event_id varchar(100) NOT NULL UNIQUE,
    payload json NOT NULL,
    received_at timestamptz NOT NULL,
    PRIMARY KEY (device_id, revision)
);
COMMIT;
