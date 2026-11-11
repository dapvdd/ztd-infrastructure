"""Authenticated provisioning API; no network calls or module execution."""

import os
import re
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import get_db
from src.provisioning.auth import admin, credential_hash, device_identity, monitoring
from src.provisioning.models import (
    ApprovalEvent,
    Assignment,
    CatalogModule,
    RegisteredDevice,
)
from src.provisioning.schemas import (
    AssignmentInput,
    Decision,
    DeviceStatus,
    Enrollment,
    EnrollmentResult,
    Manifest,
    ManifestModule,
    ModuleConfiguration,
    ModuleSpec,
    Registration,
)

router = APIRouter(prefix="/api/v2/provisioning", tags=["Provisioning v2"])


def now() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def status(device: RegisteredDevice) -> DeviceStatus:
    return DeviceStatus.model_validate(
        {
            "device_id": device.device_id,
            "hostname": device.hostname,
            "registration_status": "REGISTERED" if device.registered_at else "ENROLLED",
            "approval_status": device.approval_status,
            "approval_revision": device.approval_revision,
            "approval_expires_at": device.approval_expires_at,
            "configuration_revision": device.configuration_revision,
            "created_at": device.created_at,
            "registered_at": device.registered_at,
        }
    )


def locked_device(db: Session, device_id: str) -> RegisteredDevice:
    device = db.scalar(
        select(RegisteredDevice)
        .where(RegisteredDevice.device_id == device_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if device is None:
        raise HTTPException(404, "Provisioning device not found")
    return device


def allowed_repository(url: str) -> bool:
    return url in {
        item.strip()
        for item in os.environ.get("ZTD_MODULE_REPOSITORIES", "").split(",")
        if item.strip()
    }


def module_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,49}", name):
        raise HTTPException(422, "Invalid module name")


@router.post(
    "/devices",
    response_model=EnrollmentResult,
    status_code=201,
    dependencies=[Depends(admin)],
)
def enroll(
    payload: Enrollment, response: Response, db: Session = Depends(get_db)
) -> EnrollmentResult:
    password = secrets.token_urlsafe(32)
    timestamp = now()
    device = RegisteredDevice(
        device_id=payload.device_id,
        credential_hash=credential_hash(password),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(device)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409, "Device already enrolled; credential is not reissued"
        ) from error
    response.headers["Cache-Control"] = "no-store"
    return EnrollmentResult(**status(device).model_dump(), password=password)


@router.post("/register", response_model=DeviceStatus)
def register(
    payload: Registration,
    identity: RegisteredDevice = Depends(device_identity),
    db: Session = Depends(get_db),
) -> DeviceStatus:
    if payload.hostname != identity.device_id:
        raise HTTPException(422, "Hostname must match authenticated device identity")
    device = locked_device(db, identity.device_id)
    if device.registered_at is None:
        device.hostname = payload.hostname
        device.registered_at = now()
        device.updated_at = device.registered_at
        db.commit()
    return status(device)


@router.get("/status", response_model=DeviceStatus)
def own_status(identity: RegisteredDevice = Depends(device_identity)) -> DeviceStatus:
    return status(identity)


@router.get(
    "/devices", response_model=list[DeviceStatus], dependencies=[Depends(admin)]
)
def devices(db: Session = Depends(get_db)) -> list[DeviceStatus]:
    return [
        status(device)
        for device in db.scalars(
            select(RegisteredDevice).order_by(RegisteredDevice.device_id)
        )
    ]


@router.get(
    "/devices/{device_id}", response_model=DeviceStatus, dependencies=[Depends(admin)]
)
def details(device_id: str, db: Session = Depends(get_db)) -> DeviceStatus:
    device = db.get(RegisteredDevice, device_id)
    if device is None:
        raise HTTPException(404, "Provisioning device not found")
    return status(device)


@router.put(
    "/integrations/monitoring/devices/{device_id}/approval",
    response_model=DeviceStatus,
    dependencies=[Depends(monitoring)],
)
def external_decision(
    device_id: str, payload: Decision, db: Session = Depends(get_db)
) -> DeviceStatus:
    device = locked_device(db, device_id)
    body = payload.model_dump(mode="json")
    previous = db.get(ApprovalEvent, (device_id, payload.revision))
    if (
        previous
        and payload.revision == device.approval_revision
        and previous.payload == body
    ):
        return status(device)
    if payload.revision <= device.approval_revision:
        raise HTTPException(409, "Stale or conflicting approval revision")
    if device.registered_at is None:
        raise HTTPException(409, "Device has not registered")
    transitions = {
        "PENDING": {"APPROVED", "REJECTED", "REVOKED"},
        "APPROVED": {"APPROVED", "REVOKED"},
        "REJECTED": {"REJECTED", "REVOKED"},
        "REVOKED": {"REVOKED"},
    }
    if payload.status not in transitions[device.approval_status]:
        raise HTTPException(409, "Invalid approval transition")
    if payload.status == "APPROVED" and payload.expires_at <= now():
        raise HTTPException(422, "Decision expiry must be in the future")
    device.approval_status = payload.status
    device.approval_revision = payload.revision
    device.approval_expires_at = payload.expires_at
    db.add(
        ApprovalEvent(
            device_id=device_id,
            revision=payload.revision,
            event_id=payload.event_id,
            payload=body,
            received_at=now(),
        )
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Approval event already used") from error
    return status(device)


@router.put("/modules/{name}", response_model=ModuleSpec, dependencies=[Depends(admin)])
def put_module(
    name: str, payload: ModuleSpec, db: Session = Depends(get_db)
) -> ModuleSpec:
    module_name(name)
    if not allowed_repository(payload.repo_url):
        raise HTTPException(422, "Repository is not allowlisted")
    module = db.scalar(
        select(CatalogModule).where(CatalogModule.name == name).with_for_update()
    )
    if module is None:
        module = CatalogModule(name=name)
        db.add(module)
    module.repo_url, module.commit, module.approved = (
        payload.repo_url,
        payload.commit,
        payload.approved,
    )
    if not payload.approved:
        db.execute(
            update(Assignment)
            .where(Assignment.module_name == name)
            .values(withdrawn=True)
        )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Concurrent catalog update; retry") from error
    return payload


@router.get("/modules", dependencies=[Depends(admin)])
def modules(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return [
        {
            "name": row.name,
            "repo_url": row.repo_url,
            "commit": row.commit,
            "approved": row.approved,
        }
        for row in db.scalars(
            select(CatalogModule)
            .where(CatalogModule.approved.is_(True))
            .order_by(CatalogModule.name)
        )
        if allowed_repository(row.repo_url)
    ]


def assignment_list(db: Session, device_id: str) -> list[ManifestModule]:
    result = []
    for assignment in db.scalars(
        select(Assignment)
        .where(Assignment.device_id == device_id)
        .order_by(Assignment.module_name)
    ):
        catalog = db.get(CatalogModule, assignment.module_name)
        if (
            assignment.withdrawn
            or catalog is None
            or not catalog.approved
            or not allowed_repository(assignment.repo_url)
        ):
            raise HTTPException(409, "Assigned module is no longer approved")
        try:
            ModuleConfiguration.model_validate(assignment.configuration)
            result.append(
                ManifestModule(
                    name=assignment.module_name,
                    repo_url=assignment.repo_url,
                    commit=assignment.commit,
                    configuration=assignment.configuration,
                )
            )
        except ValidationError as error:
            raise HTTPException(409, "Persisted assignment is invalid") from error
    return result


@router.get(
    "/devices/{device_id}/assignments",
    response_model=list[ManifestModule],
    dependencies=[Depends(admin)],
)
def assignments(device_id: str, db: Session = Depends(get_db)) -> list[ManifestModule]:
    details(device_id, db)
    return assignment_list(db, device_id)


@router.put(
    "/devices/{device_id}/assignments/{name}",
    response_model=list[ManifestModule],
    dependencies=[Depends(admin)],
)
def assign(
    device_id: str, name: str, payload: AssignmentInput, db: Session = Depends(get_db)
) -> list[ManifestModule]:
    device = locked_device(db, device_id)
    catalog = db.scalar(
        select(CatalogModule).where(CatalogModule.name == name).with_for_update()
    )
    if catalog is None:
        raise HTTPException(404, "Module not found")
    if not catalog.approved or not allowed_repository(catalog.repo_url):
        raise HTTPException(409, "Module is not approved")
    configuration = payload.configuration.model_dump() if payload.configuration else {}
    assignment = db.get(Assignment, (device_id, name))
    if (
        assignment is None
        or assignment.withdrawn
        or (
            assignment.repo_url,
            assignment.commit,
            assignment.configuration,
        )
        != (catalog.repo_url, catalog.commit, configuration)
    ):
        if assignment is None:
            assignment = Assignment(device_id=device_id, module_name=name)
            db.add(assignment)
        assignment.repo_url, assignment.commit, assignment.configuration = (
            catalog.repo_url,
            catalog.commit,
            configuration,
        )
        assignment.withdrawn = False
        device.configuration_revision += 1
        device.updated_at = now()
        db.flush()
        result = assignment_list(db, device_id)
        db.commit()
        return result
    return assignment_list(db, device_id)


@router.delete(
    "/devices/{device_id}/assignments/{name}",
    status_code=204,
    dependencies=[Depends(admin)],
)
def remove_assignment(
    device_id: str, name: str, db: Session = Depends(get_db)
) -> Response:
    device = locked_device(db, device_id)
    assignment = db.get(Assignment, (device_id, name))
    if assignment is not None:
        db.delete(assignment)
        device.configuration_revision += 1
        device.updated_at = now()
        db.commit()
    return Response(status_code=204)


@router.get("/manifest", response_model=Manifest)
def manifest(
    response: Response,
    device_id: str | None = None,
    identity: RegisteredDevice = Depends(device_identity),
    db: Session = Depends(get_db),
) -> Manifest:
    if device_id is not None and device_id != identity.device_id:
        raise HTTPException(403, "Cross-device manifest access denied")
    device = locked_device(db, identity.device_id)
    if (
        not device.registered_at
        or device.approval_status != "APPROVED"
        or device.approval_expires_at is None
        or aware(device.approval_expires_at) <= now()
    ):
        raise HTTPException(403, "A current Monitoring approval is required")
    rows = assignment_list(db, device.device_id)
    response.headers["Cache-Control"] = "no-store"
    return Manifest(
        device_id=device.device_id,
        configuration_revision=device.configuration_revision,
        updated_at=device.updated_at,
        assignment_status="ASSIGNED" if rows else "EMPTY",
        modules=rows,
    )
