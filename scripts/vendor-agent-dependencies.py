"""Rebuild the offline Agent V2 wheelhouse from explicitly pinned PyPI wheels.

Run from the repository root. Review lock hashes and dependency changes before commit.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

PINS = (
    "httpx==0.28.1", "anyio==4.8.0", "certifi==2025.1.31", "httpcore==1.0.9",
    "idna==3.10", "sniffio==1.3.1", "h11==0.16.0", "typing_extensions==4.12.2",
)

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "apps" / "agent"
    target = root / "wheels"
    target.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:",
                    "--no-deps", "--index-url", "https://pypi.org/simple",
                    "--dest", str(target), *PINS], check=True)
    lines = []
    for pin in PINS:
        name, version = pin.split("==")
        wheel, = target.glob(f"{name}-{version}-*.whl")
        lines.append(f"{pin} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}")
    (root / "requirements.lock").write_text("\n".join(lines) + "\n", encoding="utf-8")
