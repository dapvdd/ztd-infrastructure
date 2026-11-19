"""Runtime primitives for the self-contained Agent V2 installer.

Only non-secret payloads are unpacked. Credentials must never pass through this
archive or its staging directory.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import tarfile
from pathlib import Path


def unpack_payload(payload: bytes, expected_digest: str, destination: Path) -> None:
    """Verify all archive metadata before writing any executable or dependency."""
    if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected_digest):
        raise ValueError("Agent payload integrity verification failed")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = archive.getmembers()
        seen: set[str] = set()
        for member in members:
            parts = member.name.split("/")
            allowed = member.name in {"agent_v2.py", "hubbrain_adapter.py", "requirements.lock"}
            allowed = allowed or (len(parts) == 2 and parts[0] == "wheels"
                                  and parts[1].endswith(".whl") and parts[1] not in {".", ".."})
            if (not allowed or not member.isfile() or "\\" in member.name
                    or member.name in seen or member.size > 10_000_000):
                raise ValueError("Invalid Agent payload member")
            seen.add(member.name)
        for member in members:
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            with target.open("xb") as output:
                output.write(archive.extractfile(member).read())
            target.chmod(0o644)
