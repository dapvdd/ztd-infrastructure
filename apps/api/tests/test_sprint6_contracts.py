"""Sprint 6 PR01 — ZTD-owned contract fixtures.

All v3 content here is a ZTD proposal (ztd_proposal). Monitoring facts are
marked source_verified and cite the pinned public source. No production route,
schema, credential issuer or callback sender is created by this module.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args
from urllib.parse import urlsplit

import pytest
import yaml
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "sprint6"
SCHEMAS = ROOT / "docs" / "sprint6" / "schemas"
OPENAPI = ROOT / "docs" / "sprint6" / "openapi-v3.yaml"
SCHEMA_CONFORMANCE_NOTE = (
    "PROPOSAL_STRUCTURAL_ONLY; temporal/cross-field invariants are enforced by "
    "the test-module Pydantic validators, not by JSON Schema 2020-12; no "
    "conforming validator is installed in this environment"
)


def load_fixture(name):
    return json.loads(FIXTURES.joinpath(name).read_text(encoding="utf-8"))


def load_schema(name):
    return json.loads(SCHEMAS.joinpath(name).read_text(encoding="utf-8"))


class StrictProposal(BaseModel):
    """Test-only base for every proposed v3 contract model.

    extra=forbid is what makes binding/authorization/monitoring/hub_key and
    mqtt_pass impossible at any level; the evidence label is emitted into the
    generated JSON Schema so the committed document cannot silently lose it.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"x-evidence": "ztd_proposal"},
    )


class ReleaseDescriptor(StrictProposal):
    release_id: str = Field(min_length=1, max_length=100)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    archive_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    os_id: str = Field(min_length=1, max_length=50)
    architecture: str = Field(min_length=1, max_length=50)


class BrokerSpec(StrictProposal):
    """Nonsecret local-broker addressing plus a credential reference.

    mqtt_user is mandatory and nonsecret; the secret itself is only a version
    handle, never a value (mirrors the v2 HubConfig omission rationale).
    """

    mqtt_user: str = Field(min_length=1, max_length=100)
    credential_version: str = Field(min_length=1, max_length=100)
    mqtt_host: str = Field(min_length=1, max_length=253)
    mqtt_port: int = Field(ge=1, le=65535)


class RuntimeSpec(StrictProposal):
    release_id: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=100)


class CacheSpec(StrictProposal):
    path: str = Field(min_length=1, max_length=256)
    max_pending_rows: int = Field(ge=1, le=1_000_000)


class ServiceSpec(StrictProposal):
    unit: str = Field(min_length=1, max_length=100)


class AssignmentSpec(StrictProposal):
    name: str = Field(min_length=1, max_length=100)
    operation: Literal["ensure_present", "ensure_absent", "configure"]
    executor: str = Field(min_length=1, max_length=100)
    release_id: str = Field(min_length=1, max_length=100)


class RollbackPolicy(StrictProposal):
    retained_revisions: int = Field(ge=1, le=10)
    previous_release_ids: list[str] = Field(default_factory=list)


class LocalPlanModel(StrictProposal):
    model_config = ConfigDict(
        json_schema_extra={
            "x-evidence": "ztd_proposal",
            "x-schema-conformance": SCHEMA_CONFORMANCE_NOTE,
            "x-runtime-invariants": ["expires_at must be after issued_at"],
        }
    )

    schema_version: Literal["3"]
    stage: Literal["LOCAL_INSTALL"]
    device_id: str = Field(pattern=r"^raspi-[a-z0-9-]{3,20}$")
    plan_id: str = Field(min_length=1, max_length=100)
    desired_revision: int = Field(ge=1)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    required_agent_version: str = Field(min_length=1, max_length=100)
    capabilities: list[str] = Field(min_length=1)
    releases: list[ReleaseDescriptor] = Field(min_length=1)
    broker: BrokerSpec
    runtime: RuntimeSpec
    cache: CacheSpec
    services: list[ServiceSpec]
    assignments: list[AssignmentSpec]
    rollback_policy: RollbackPolicy

    @model_validator(mode="after")
    def expires_after_issued(self):
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        return self


def local_plan_schema():
    """Committed LOCAL_INSTALL JSON Schema with transport-only keys attached."""

    doc = LocalPlanModel.model_json_schema()
    doc["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    doc["$id"] = "https://ztd.invalid/schemas/sprint6/commissioning-plan.json"
    return doc


class Binding(StrictProposal):
    """Owner-attested device-to-hub mapping; never derived from device_id."""

    monitoring_instance_id: str = Field(min_length=1, max_length=100)
    binding_id: str = Field(min_length=1, max_length=100)
    binding_generation: int = Field(ge=1)
    hub_id: str = Field(min_length=1, max_length=100)


class Authorization(StrictProposal):
    model_config = ConfigDict(populate_by_name=True)

    approval_revision: int = Field(ge=1)
    expires_at: AwareDatetime
    credential_version: str = Field(min_length=1, max_length=100)
    x_no_connectivity_inference: Literal[True] = Field(
        alias="x-no-connectivity-inference"
    )


class MonitoringUrls(StrictProposal):
    """Nonsecret full URLs mapped to pinned source env keys (never invented)."""

    ingest_url: str = Field(pattern=r"^https://[^\s]+$")
    devices_url: str = Field(pattern=r"^https://[^\s]+$")
    commands_url: str = Field(pattern=r"^https://[^\s]+$")
    unapproved_url: str = Field(pattern=r"^https://[^\s]+$")
    ca_artifact_id: str = Field(min_length=1, max_length=100)


class SecretRef(StrictProposal):
    """Opaque recipient-bound handle only; no secret value is representable."""

    role: str = Field(min_length=1, max_length=100)
    envelope_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)


class OperationalManifestModel(LocalPlanModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "x-evidence": "ztd_proposal",
            "x-schema-conformance": SCHEMA_CONFORMANCE_NOTE,
            "x-runtime-invariants": [
                "expires_at must be after issued_at",
                "authorization.expires_at must be after issued_at",
                "binding.hub_id must not equal device_id (identity derivation)",
            ],
            "x-binding-authority": "NOT_MONITORING_AUTHORIZED",
        },
    )

    stage: Literal["OPERATIONAL"]
    binding: Binding
    authorization: Authorization
    monitoring: MonitoringUrls
    secret_refs: list[SecretRef]
    x_evidence: Literal["ztd_proposal"] = Field(alias="x-evidence")

    @model_validator(mode="after")
    def approval_after_issued(self):
        if self.authorization.expires_at <= self.issued_at:
            raise ValueError("authorization expiry must be after issue")
        return self

    @model_validator(mode="after")
    def binding_is_not_derived_from_device_id(self):
        if self.binding.hub_id == self.device_id:
            raise ValueError("binding.hub_id must not equal device_id")
        return self


def operational_manifest_schema():
    doc = OperationalManifestModel.model_json_schema()
    doc["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    doc["$id"] = "https://ztd.invalid/schemas/sprint6/operational-manifest.json"
    return doc


class ModuleResult(StrictProposal):
    name: str = Field(min_length=1, max_length=100)
    result: Literal["succeeded", "failed", "rolled_back", "skipped"]
    digest: str | None = None


class ExecutionEventModel(StrictProposal):
    model_config = ConfigDict(
        json_schema_extra={
            "x-evidence": "ztd_proposal",
            "x-schema-conformance": SCHEMA_CONFORMANCE_NOTE,
            "x-runtime-invariants": [
                "(desired_revision, content_digest) must equal "
                "(plan_revision, plan_digest)"
            ],
        }
    )

    schema_version: Literal["3"]
    event_id: str = Field(min_length=1, max_length=100)
    device_id: str = Field(pattern=r"^raspi-[a-z0-9-]{3,20}$")
    stage: Literal["LOCAL_INSTALL", "OPERATIONAL"]
    plan_id: str = Field(min_length=1, max_length=100)
    desired_revision: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    plan_revision: int = Field(ge=1)
    plan_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    binding_generation: int | None = Field(default=None, ge=1)
    attempt_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    result: Literal[
        "RECEIVED", "IN_PROGRESS", "LOCAL_APPLIED", "FAILED", "ROLLED_BACK"
    ]
    module_results: list[ModuleResult]
    artifact_digests: list[str]
    previous_safe_release: str | None = None
    error_code: str | None = None
    disposition: str | None = None
    device_timestamp: AwareDatetime
    boot_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def issued_snapshot_tuple_is_immutable(self):
        if (self.desired_revision, self.content_digest) != (
            self.plan_revision,
            self.plan_digest,
        ):
            raise ValueError("event must reference the exact issued snapshot tuple")
        return self


def execution_event_schema():
    doc = ExecutionEventModel.model_json_schema()
    doc["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    doc["$id"] = "https://ztd.invalid/schemas/sprint6/execution-event.json"
    return doc


class ApprovalEventModel(StrictProposal):
    """Immutable proposed callback body. No sender is assumed to exist."""

    model_config = ConfigDict(
        json_schema_extra={
            "x-evidence": "ztd_proposal",
            "x-monitoring-sender": "DOES_NOT_EXIST_AT_PINNED_SOURCE",
            "x-approval-gate": "M04/M10",
            "x-no-connectivity-inference": True,
            "x-schema-conformance": SCHEMA_CONFORMANCE_NOTE,
            "x-runtime-invariants": [
                "APPROVED expiry must be after the receiver-supplied receipt time "
                "(explicit, never wall-clock)",
            ],
            "allOf": [
                {
                    "if": {
                        "properties": {"status": {"const": "APPROVED"}},
                        "required": ["status"],
                    },
                    "then": {
                        "properties": {
                            "expires_at": {"type": "string", "format": "date-time"}
                        },
                        "required": ["expires_at"],
                    },
                }
            ],
        }
    )

    schema_version: Literal["3"]
    event_id: str = Field(min_length=1, max_length=100)
    monitoring_instance_id: str = Field(min_length=1, max_length=100)
    device_id: str = Field(pattern=r"^raspi-[a-z0-9-]{3,20}$")
    hub_id: str = Field(min_length=1, max_length=100)
    binding_id: str = Field(min_length=1, max_length=100)
    binding_generation: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    status: Literal["APPROVED", "REJECTED", "REVOKED"]
    actor: str = Field(min_length=1, max_length=100)
    occurred_at: AwareDatetime
    expires_at: AwareDatetime | None
    credential_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def approved_requires_expiry(self):
        if self.status == "APPROVED" and self.expires_at is None:
            raise ValueError("APPROVED requires a non-null expires_at")
        return self


def validate_approval_event(payload, receipt_time):
    """Validate against an explicit receiver time, never wall-clock time."""

    event = ApprovalEventModel.model_validate(payload)
    if event.status == "APPROVED" and event.expires_at <= receipt_time:
        raise ValueError("APPROVED expiry must be after the receiver time")
    return event


def approval_event_schema():
    doc = ApprovalEventModel.model_json_schema()
    doc["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    doc["$id"] = "https://ztd.invalid/schemas/sprint6/approval-event.json"
    return doc


def strip_schema_transport(doc):
    """Normalize transport-only keys before comparing schema to model output."""

    result = json.loads(json.dumps(doc))
    for key in ("$schema", "$id"):
        result.pop(key, None)
    return result


def external_refs(node):
    """Collect every non-fragment $ref in an OpenAPI document."""

    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and not value.startswith("#"):
                found.add(value)
            else:
                found.update(external_refs(value))
    elif isinstance(node, list):
        for item in node:
            found.update(external_refs(item))
    return found


def structural_validate(instance, schema, root=None, path="$"):
    """Minimal JSON Schema 2020-12 SUBSET checker — NOT a conforming validator.

    Covers only keywords Pydantic emits for the four PR01 schemas: local $ref,
    type, anyOf, allOf/if/then, const, enum, pattern, length and numeric bounds,
    items, required, properties and additionalProperties. `format` is treated
    as annotation-only, as JSON Schema 2020-12 specifies. Cross-field and
    temporal rules are deliberately out of scope; they are annotated in each
    committed schema as x-runtime-invariants and enforced by the test-module
    Pydantic validators. Returns a list of violations (empty == checked OK).
    """

    root = root if root is not None else schema
    errors = []

    def type_matches(value, expected):
        predicates = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
        }
        return predicates[expected](value)

    def check(node, value, at):
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/"):
                errors.append(f"{at}: unsupported external $ref {ref}")
                return
            target = root
            for token in ref[2:].split("/"):
                target = target[token.replace("~1", "/").replace("~0", "~")]
            check(target, value, at)
            return
        if "anyOf" in node and not any(
            not structural_validate(value, branch, root, at)
            for branch in node["anyOf"]
        ):
            errors.append(f"{at}: no anyOf branch matched")
        for branch in node.get("allOf", []):
            if "if" in branch:
                if not structural_validate(value, branch["if"], root, at):
                    check(branch["then"], value, f"{at}.then")
            else:
                check(branch, value, at)
        expected = node.get("type")
        if expected is not None:
            expected_types = expected if isinstance(expected, list) else [expected]
            if not any(type_matches(value, t) for t in expected_types):
                errors.append(f"{at}: expected {expected_types}, got {type(value).__name__}")
                return
        if "const" in node and value != node["const"]:
            errors.append(f"{at}: const mismatch")
        if "enum" in node and value not in node["enum"]:
            errors.append(f"{at}: outside enum")
        if isinstance(value, str):
            if "pattern" in node and re.search(node["pattern"], value) is None:
                errors.append(f"{at}: pattern mismatch")
            if "minLength" in node and len(value) < node["minLength"]:
                errors.append(f"{at}: shorter than minLength")
            if "maxLength" in node and len(value) > node["maxLength"]:
                errors.append(f"{at}: longer than maxLength")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in node and value < node["minimum"]:
                errors.append(f"{at}: below minimum")
            if "maximum" in node and value > node["maximum"]:
                errors.append(f"{at}: above maximum")
        if isinstance(value, list):
            if "minItems" in node and len(value) < node["minItems"]:
                errors.append(f"{at}: fewer than minItems")
            for index, item in enumerate(value):
                if "items" in node:
                    check(node["items"], item, f"{at}[{index}]")
        if isinstance(value, dict):
            properties = node.get("properties", {})
            for name, subschema in properties.items():
                if name in value:
                    check(subschema, value[name], f"{at}.{name}")
            for name in node.get("required", []):
                if name not in value:
                    errors.append(f"{at}: missing required {name}")
            if node.get("additionalProperties") is False:
                for name in value:
                    if name not in properties:
                        errors.append(f"{at}: additional property {name}")

    check(schema, instance, path)
    return errors


def test_source_fact_names_are_exact():
    facts = json.loads(FIXTURES.joinpath("monitoring-source-facts.json").read_text())
    assert facts["evidence"] == "source_verified"
    assert facts["commit"] == "3afa0a954fac1b92cf9df7a29ed13bc82b5352e6"
    assert set(facts["env_keys"]) >= {
        "HUB_KEY", "HUB_ID", "MQTT_USER", "MQTT_PASS", "MQTT_HOST", "MQTT_PORT",
        "MQTT_TOPIC", "SERVER_URL", "SERVER_DEVICES_URL", "SERVER_COMMANDS_URL",
        "SERVER_UNAPPROVED_URL", "TLS_CERT_PATH", "EDGE_CACHE_DB_PATH",
        "MAX_PENDING_ROWS", "REPLAY_BATCH_SIZE", "REPLAY_PACING_DELAY",
        "REPLAY_INTERVAL", "ALLOW_INSECURE_DEV_KEYS",
    }
    assert set(facts["endpoints"]) == {
        "POST /api/iot", "GET /api/devices", "GET /api/hub/commands",
        "POST /api/iot/unapproved",
    }
    assert facts["headers"] == ["X-Hub-ID", "X-Hub-Key"]
    assert facts["defaults"]["MQTT_TOPIC"] == "hs109rs/#"
    assert facts["defaults"]["MAX_PENDING_ROWS"] == 20000


def test_drift_names_rejected():
    negatives = json.loads(FIXTURES.joinpath("monitoring-source-drift-negatives.json").read_text())
    assert negatives["evidence"] == "source_verified"
    assert set(negatives["names"]) >= {
        "SERVER_ALERT_URL", "HUB_NAME", "/api/iot/telemetry", "hub/V5/main.py",
    }
    assert "ALLOW_INSECURE_DEV_KEYS=true" in negatives["names"]
    assert negatives["rule"] == "negative_evidence_only_not_configuration"


def test_v2_contract_unchanged():
    from src.provisioning.schemas import Decision, HubConfig, Manifest

    assert Manifest.model_fields["schema_version"].default == "2"
    assert get_args(Decision.model_fields["schema_version"].annotation) == ("1",)
    assert set(HubConfig.model_fields) == {"hub_id", "server_url", "mqtt_host", "mqtt_port"}
    assert HubConfig.model_config.get("extra") == "forbid"
    assert "mqtt_user" not in HubConfig.model_fields
    assert Manifest.model_fields["hub_config"].annotation.__args__[0] is HubConfig

    from src.main import app

    prefix = "/api/v2/provisioning"
    pinned = {
        (f"{prefix}/devices", "POST"),
        (f"{prefix}/devices", "GET"),
        (f"{prefix}/register", "POST"),
        (f"{prefix}/status", "GET"),
        (f"{prefix}/devices/{{device_id}}", "GET"),
        (
            f"{prefix}/integrations/monitoring/devices/{{device_id}}/approval",
            "PUT",
        ),
        (f"{prefix}/modules/{{name}}", "PUT"),
        (f"{prefix}/modules", "GET"),
        (f"{prefix}/devices/{{device_id}}/assignments", "GET"),
        (f"{prefix}/devices/{{device_id}}/assignments/{{name}}", "PUT"),
        (f"{prefix}/devices/{{device_id}}/assignments/{{name}}", "DELETE"),
        (f"{prefix}/manifest", "GET"),
    }
    registered = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if getattr(route, "path", "").startswith(prefix)
    }
    assert registered == pinned
    assert not any(
        getattr(route, "path", "").startswith("/api/v3/") for route in app.routes
    )


def test_local_plan_cannot_activate_upstream():
    plan = load_fixture("commissioning-plan.local.valid.json")
    assert plan["stage"] == "LOCAL_INSTALL"
    for forbidden in ("binding", "authorization", "monitoring", "hub_key"):
        assert forbidden not in plan
    with pytest.raises(ValidationError):
        LocalPlanModel.model_validate(
            load_fixture("commissioning-plan.local.invalid-upstream.json")
        )


def test_missing_mqtt_user():
    with pytest.raises(ValidationError):
        LocalPlanModel.model_validate(
            load_fixture("commissioning-plan.local.invalid-no-mqtt-user.json")
        )


def test_unknown_schema_rejected():
    base = load_fixture("commissioning-plan.local.valid.json")
    with pytest.raises(ValidationError):
        LocalPlanModel.model_validate({**base, "schema_version": "4"})
    with pytest.raises(ValidationError):
        LocalPlanModel.model_validate({**base, "stage": "OPERATIONAL"})
    with pytest.raises(ValidationError):
        LocalPlanModel.model_validate({**base, "extra_key": 1})


def test_local_plan_schema_matches_committed_document():
    doc = load_schema("commissioning-plan.json")
    assert doc["x-evidence"] == "ztd_proposal"
    assert doc["additionalProperties"] is False
    assert strip_schema_transport(doc) == LocalPlanModel.model_json_schema()


def test_operational_schema_matches_committed_document():
    doc = load_schema("operational-manifest.json")
    assert doc["x-evidence"] == "ztd_proposal"
    assert doc["additionalProperties"] is False
    assert strip_schema_transport(doc) == OperationalManifestModel.model_json_schema()


def test_execution_event_schema_matches_committed_document():
    doc = load_schema("execution-event.json")
    assert doc["x-evidence"] == "ztd_proposal"
    assert doc["additionalProperties"] is False
    assert strip_schema_transport(doc) == ExecutionEventModel.model_json_schema()


def test_approval_schema_matches_committed_document():
    doc = load_schema("approval-event.json")
    assert doc["x-evidence"] == "ztd_proposal"
    assert doc["additionalProperties"] is False
    assert strip_schema_transport(doc) == ApprovalEventModel.model_json_schema()


def test_operational_requires_mapping_approval():
    with pytest.raises(ValidationError):
        OperationalManifestModel.model_validate(
            load_fixture("operational-manifest.no-approval.json")
        )
    valid = OperationalManifestModel.model_validate(
        load_fixture("operational-manifest.proposed.valid.json")
    )
    assert valid.binding.binding_generation >= 1
    assert valid.authorization.approval_revision >= 1
    assert valid.authorization.expires_at > valid.issued_at


def test_approval_not_connectivity():
    manifest = load_fixture("operational-manifest.proposed.valid.json")
    assert "operational_verified" not in manifest
    assert "connected" not in manifest
    assert manifest["x-evidence"] == "ztd_proposal"
    assert manifest["authorization"]["x-no-connectivity-inference"] is True


def test_202_is_not_approval():
    facts = load_fixture("monitoring-source-facts.json")
    assert "202 pending_approval" in facts["authority_notes"]["not_approval"]
    assert "GET /api/devices" in facts["authority_notes"]["not_approval"]
    assert (
        "POST /api/hub/commands/{id}/delivered"
        in facts["authority_notes"]["not_approval"]
    )
    doc = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    response_codes = {
        code
        for item in doc["paths"].values()
        for operation in item.values()
        if isinstance(operation, dict)
        for code in operation.get("responses", {})
    }
    assert "202" not in response_codes
    assert "PENDING" not in load_schema("approval-event.json")["properties"]["status"][
        "enum"
    ]


def test_no_generated_hub_key():
    schema = load_schema("operational-manifest.json")
    assert "hub_key" not in json.dumps(schema)
    assert "hub_key" not in json.dumps(
        load_fixture("operational-manifest.proposed.valid.json")
    )
    assert "envelope_id" in json.dumps(schema)


def test_binding_identity_derivation_is_prohibited_invariant():
    """binding.hub_id == device_id is a runtime-prohibited identity derivation.

    This test-only invariant does NOT establish Monitoring-authorized binding;
    no Monitoring binding API or owner attestation is assumed to exist.
    """

    negative = load_fixture("operational-manifest.derived-hub-id.json")
    assert "hub_id" not in negative, (
        "negative fixture must fail on binding.hub_id, not an extra top-level key"
    )
    assert negative["binding"]["hub_id"] == negative["device_id"]
    with pytest.raises(ValidationError) as excinfo:
        OperationalManifestModel.model_validate(negative)
    assert "binding.hub_id must not equal device_id" in str(excinfo.value)

    schema = load_schema("operational-manifest.json")
    assert any(
        "binding.hub_id" in invariant and "device_id" in invariant
        for invariant in schema["x-runtime-invariants"]
    )
    assert schema["x-binding-authority"] == "NOT_MONITORING_AUTHORIZED"


def test_canonical_digest_vectors():
    vectors = load_fixture("canonical-digest-vectors.json")
    for case in vectors["cases"]:
        digest = hashlib.sha256(case["canonical_bytes"].encode("utf-8")).hexdigest()
        assert f"sha256:{digest}" == case["content_digest"]
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", case["content_digest"])
    assert vectors["cases"][0]["content_digest"] != vectors["cases"][1]["content_digest"]
    assert vectors["cases"][2]["content_digest"] == vectors["cases"][0]["content_digest"]


def test_signature_input_vector():
    vector = load_fixture("signature-input-vector.json")
    assert vector["evidence"] == "ztd_proposal"
    assert vector["algorithm"] == "HMAC-SHA256"
    assert vector["test_key_is_synthetic"] is True
    expected = hashlib.sha256(vector["raw_body"].encode("utf-8")).hexdigest()
    assert vector["inputs"]["body_sha256"] == expected
    assert vector["inputs"]["method"] == "PUT"
    assert vector["headers"]["key_id"].startswith("test-only-")


def test_signature_vector_does_not_freeze_wire_format():
    vector = load_fixture("signature-input-vector.json")
    assert vector["x-wire-format-status"] == "NOT_FROZEN_PENDING_M04_M10"
    assert "length-delimited encoding is specified" not in vector["x-note"]
    assert "proposed_field_order" in vector["inputs"]
    assert "field_order" not in vector["inputs"]


def test_execution_event_tuple_and_no_secrets():
    event = ExecutionEventModel.model_validate(load_fixture("execution-event.valid.json"))
    assert (event.desired_revision, event.content_digest) == (
        event.plan_revision, event.plan_digest,
    )
    dumped = json.dumps(event.model_dump(mode="json"))
    for leaked in ("hub_key", "mqtt_pass", "password", "Authorization"):
        assert leaked not in dumped


def test_absent_sender_authentication_is_unverified():
    """A valid proposed body is not evidence of an authenticated sender."""
    schema = load_schema("approval-event.json")
    assert schema["x-evidence"] == "ztd_proposal"
    assert schema["x-monitoring-sender"] == "DOES_NOT_EXIST_AT_PINNED_SOURCE"
    assert schema["x-approval-gate"] == "M04/M10"
    absent = load_fixture("approval-event.absent-sender.json")
    assert absent["authentication_verification"] == "UNVERIFIED_NOT_TESTED"
    assert absent["expected_ztd_status"] == "UNKNOWN"
    # UNKNOWN is a proposed expectation, not an executed authentication decision.
    assert ApprovalEventModel.model_validate(absent["payload"]).status == "APPROVED"


def test_proposed_approval_event_fields():
    event = ApprovalEventModel.model_validate(
        load_fixture("approval-event.proposed.json")
    )
    assert event.schema_version == "3"
    assert event.status in {"APPROVED", "REJECTED", "REVOKED"}
    assert event.binding_generation >= 1
    assert event.hub_id != event.device_id
    assert "hub_key" not in json.dumps(event.model_dump(mode="json"))


def test_approval_expiry_uses_supplied_receipt_time():
    payload = load_fixture("approval-event.proposed.json")
    receipt = datetime(2026, 11, 19, 10, 5, tzinfo=UTC)
    assert validate_approval_event(payload, receipt).status == "APPROVED"
    stale = {**payload, "expires_at": "2026-11-19T10:00:00Z"}
    with pytest.raises(ValueError):
        validate_approval_event(stale, receipt)


def test_approved_null_expiry_rejected_for_every_status_policy():
    """APPROVED may not carry a null expiry; REJECTED/REVOKED still may."""

    payload = load_fixture("approval-event.proposed.json")
    receipt = datetime(2026, 11, 19, 10, 5, tzinfo=UTC)
    null_expiry = {**payload, "expires_at": None}
    with pytest.raises(ValidationError):
        ApprovalEventModel.model_validate(null_expiry)
    with pytest.raises(ValueError):
        validate_approval_event(null_expiry, receipt)
    for status in ("REJECTED", "REVOKED"):
        negative = {**payload, "status": status, "expires_at": None}
        assert validate_approval_event(negative, receipt).status == status


def test_openapi_references_only_proposed_contracts():
    doc = yaml.safe_load(OPENAPI.read_text())
    assert doc["openapi"] == "3.1.0"
    assert doc["info"]["x-evidence"] == "ztd_proposal"
    serialized = json.dumps(doc)
    for forbidden in (
        "SERVER_ALERT_URL",
        "HUB_NAME",
        "/api/iot/telemetry",
        "hub/V5/main.py",
    ):
        assert forbidden not in serialized
    assert external_refs(doc) == {
        f"schemas/{name}.json"
        for name in (
            "commissioning-plan",
            "operational-manifest",
            "execution-event",
            "approval-event",
        )
    }
    assert (
        doc["components"]["securitySchemes"]["MonitoringSender"]["x-status"]
        == "PROPOSED_NO_SENDER"
    )


def test_openapi_external_refs_resolve_from_document_directory():
    """Each $ref must resolve from the OpenAPI file's own directory and parse."""

    doc = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    refs = external_refs(doc)
    assert refs, "expected at least one external schema reference"
    for ref in sorted(refs):
        assert not ref.startswith(("/", "docs/")), f"ref must be document-relative: {ref}"
        target = (OPENAPI.parent / ref).resolve()
        assert target.is_file(), f"unresolved OpenAPI $ref: {ref} -> {target}"
        schema = json.loads(target.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["x-evidence"] == "ztd_proposal"


def test_approval_gates_declared():
    doc = yaml.safe_load(OPENAPI.read_text())
    gates = {path: value["x-approval-gate"] for path, value in doc["paths"].items()}
    assert gates["/api/v3/provisioning/operational_manifest"] == "M01/M02/M04/M05/M06/M08"
    assert gates["/api/v3/provisioning/integrations/monitoring/approval_events/{event_id}"] == "M04/M10"
    assert gates["/api/v3/provisioning/commissioning_plan"] == "NONE_ZTD_LOCAL_ONLY"
    assert all("application/problem+json" in json.dumps(op) for op in doc["paths"].values())


def test_openapi_operations_have_ids_and_documented_auth():
    doc = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    assert "issuer" in doc["info"]["x-auth-model"].lower()
    assert "sender" in doc["info"]["x-auth-model"].lower()

    operations = []
    for path, item in doc["paths"].items():
        for method, operation in item.items():
            if isinstance(operation, dict):
                operations.append((path, method, operation))
    assert operations
    ids = [operation["operationId"] for _, _, operation in operations]
    assert len(ids) == len(set(ids)), "operationId must be unique"
    for path, method, operation in operations:
        assert re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", operation["operationId"])
        assert "security" in operation, f"{method} {path}: security must be explicit"
        assert operation["x-auth-status"], f"{method} {path}: x-auth-status required"

    schemes = doc["components"]["securitySchemes"]
    assert schemes["DeviceBearer"]["x-status"] == "PROPOSED_NO_ISSUER"
    assert schemes["AdminBearer"]["x-status"] == "PROPOSED_NO_ISSUER"
    assert schemes["MonitoringSender"]["x-status"] == "PROPOSED_NO_SENDER"


def test_consumer_side_checks_enforce_schema_expressible_constraints():
    """Committed schemas reject expressible negatives without a full validator."""

    pairs = {
        "commissioning-plan": "commissioning-plan.local.valid.json",
        "operational-manifest": "operational-manifest.proposed.valid.json",
        "execution-event": "execution-event.valid.json",
        "approval-event": "approval-event.proposed.json",
    }
    for schema_name, fixture_name in pairs.items():
        assert structural_validate(
            load_fixture(fixture_name), load_schema(f"{schema_name}.json")
        ) == [], f"valid fixture must satisfy {schema_name}"

    approval_schema = load_schema("approval-event.json")
    base = load_fixture("approval-event.proposed.json")
    for label, mutation in (
        ("null APPROVED expiry", {"expires_at": None}),
        ("unknown status", {"status": "PENDING"}),
        ("extra field", {"extra": 1}),
        ("nonpositive revision", {"revision": 0}),
    ):
        assert structural_validate(
            {**base, **mutation}, approval_schema
        ), f"expressible negative must fail: {label}"


def test_cross_field_invariants_require_runtime_validation():
    """The subset checker cannot see temporal/tuple rules; Pydantic must."""

    for schema_name in (
        "commissioning-plan",
        "operational-manifest",
        "execution-event",
        "approval-event",
    ):
        schema = load_schema(f"{schema_name}.json")
        assert schema["x-schema-conformance"] == SCHEMA_CONFORMANCE_NOTE
        assert schema["x-runtime-invariants"], schema_name

    plan = load_fixture("commissioning-plan.local.valid.json")
    stale_plan = {**plan, "expires_at": "2026-11-19T09:00:00Z"}
    assert structural_validate(
        stale_plan, load_schema("commissioning-plan.json")
    ) == [], "temporal ordering is not expressible in JSON Schema 2020-12"
    with pytest.raises(ValidationError):
        LocalPlanModel.model_validate(stale_plan)

    event = load_fixture("execution-event.valid.json")
    mismatched = {**event, "plan_digest": "sha256:" + "0" * 64}
    assert structural_validate(
        mismatched, load_schema("execution-event.json")
    ) == [], "snapshot-tuple equality is not expressible in JSON Schema 2020-12"
    with pytest.raises(ValidationError):
        ExecutionEventModel.model_validate(mismatched)

    approval = load_fixture("approval-event.proposed.json")
    stale = {**approval, "expires_at": "2026-11-19T10:00:00Z"}
    assert structural_validate(
        stale, load_schema("approval-event.json")
    ) == [], "receipt-relative freshness is not expressible in JSON Schema 2020-12"
    with pytest.raises(ValueError):
        validate_approval_event(stale, datetime(2026, 11, 19, 10, 5, tzinfo=UTC))


def test_source_facts_and_drift_negatives_gate_contract_artifacts():
    """Pinned source facts constrain real fixtures, not just their own file."""

    facts = load_fixture("monitoring-source-facts.json")
    negatives = load_fixture("monitoring-source-drift-negatives.json")
    # hub/main.py:61-72 at 3afa0a954fac1b92cf9df7a29ed13bc82b5352e6.
    # Source compatibility only: these defaults do not establish owner approval.
    endpoint_roles = {
        "ingest_url": "/api/iot",
        "devices_url": "/api/devices",
        "commands_url": "/api/hub/commands",
        "unapproved_url": "/api/iot/unapproved",
    }
    assert {entry.split(" ", 1)[1] for entry in facts["endpoints"]} == set(endpoint_roles.values())

    for fixture_path in sorted(FIXTURES.glob("*.json")):
        if fixture_path.name.startswith("monitoring-source-"):
            continue
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        monitoring = data.get("monitoring") or data.get("payload", {}).get("monitoring")
        if not monitoring:
            continue
        for field, url in monitoring.items():
            assert field in {
                "ingest_url", "devices_url", "commands_url", "unapproved_url",
                "ca_artifact_id",
            }, f"{fixture_path.name}: unexpected monitoring field {field}"
            if field == "ca_artifact_id":
                continue
            assert isinstance(url, str) and url.startswith("https://"), (
                f"{fixture_path.name}: {field} must be an illustrative HTTPS URL"
            )
            parsed = urlsplit(url)
            assert parsed.path == endpoint_roles[field], (
                f"{fixture_path.name}: endpoint role mismatch for {field}: "
                f"expected {endpoint_roles[field]}, got {parsed.path}"
            )
            assert parsed.hostname.endswith(".invalid"), (
                f"{fixture_path.name}: non-illustrative host: {url}"
            )
            for drift in negatives["names"]:
                if drift.startswith("/"):
                    assert drift not in url, (
                        f"{fixture_path.name}: drift endpoint adopted: {drift}"
                    )


@pytest.mark.parametrize("left,right", [
    ("ingest_url", "devices_url"),
    ("ingest_url", "commands_url"),
    ("ingest_url", "unapproved_url"),
    ("devices_url", "commands_url"),
    ("devices_url", "unapproved_url"),
    ("commands_url", "unapproved_url"),
])
def test_source_gate_rejects_swapped_endpoint_roles(monkeypatch, left, right):
    """The actual artifact gate must reject source-valid paths in wrong roles."""
    original = Path.read_text

    def read_mutated(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        if path == FIXTURES / "operational-manifest.proposed.valid.json":
            data = json.loads(text)
            urls = data["monitoring"]
            urls[left], urls[right] = urls[right], urls[left]
            return json.dumps(data)
        return text

    monkeypatch.setattr(Path, "read_text", read_mutated)
    with pytest.raises(AssertionError, match="endpoint role mismatch"):
        test_source_facts_and_drift_negatives_gate_contract_artifacts()


@pytest.mark.parametrize("field", [
    "ingest_url", "devices_url", "commands_url", "unapproved_url",
])
def test_source_gate_rejects_invented_endpoint_paths(monkeypatch, field):
    original = Path.read_text

    def read_mutated(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        if path == FIXTURES / "operational-manifest.proposed.valid.json":
            data = json.loads(text)
            data["monitoring"][field] = "https://monitoring.example.invalid/api/iot/telemetry"
            return json.dumps(data)
        return text

    monkeypatch.setattr(Path, "read_text", read_mutated)
    with pytest.raises(AssertionError):
        test_source_facts_and_drift_negatives_gate_contract_artifacts()
