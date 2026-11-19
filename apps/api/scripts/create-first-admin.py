#!/usr/bin/env python3
"""Sprint 5 — secure first-admin bootstrap (one-shot, out-of-band).

Run INSIDE the backend container (no public endpoint ever exists):

    docker compose exec backend python /app/scripts/create-first-admin.py

Behavior:
- Prompts on the terminal (getpass; never echoed, never in argv/logs).
- Enforces the same password policy as the API (service.password_policy_error).
- Refuses to run if an ADMIN already exists unless --force is passed twice.
- Writes an Argon2id hash into app_users and an ADMIN_BOOTSTRAPPED audit row.

Optional non-interactive env (for automation WITHOUT shell history):
    ZTD_BOOTSTRAP_USERNAME, ZTD_BOOTSTRAP_PASSWORD
The password from env is consumed once and MUST be >= policy; still never
logged. Prefer the interactive prompt.
"""

from __future__ import annotations

import argparse
import getpass
import sys

IGNORE = sys.modules[__name__]


def _prompt_username(default: str) -> str:
    try:
        raw = input(f"Username [{default}]: ").strip()
    except EOFError:
        return default
    return raw or default


def _prompt_password(twice: bool = True) -> str:
    pw = getpass.getpass("Password (input hidden): ")
    if twice:
        confirm = getpass.getpass("Confirm password: ")
        if pw != confirm:
            print("ERROR: passwords do not match.", file=sys.stderr)
            sys.exit(2)
    return pw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--username", default=os_env_default("ZTD_BOOTSTRAP_USERNAME", "admin"),
        help="admin username (default: env ZTD_BOOTSTRAP_USERNAME or 'admin')",
    )
    parser.add_argument(
        "--password-stdin", action="store_true",
        help="read the password from stdin (one line) instead of prompting",
    )
    parser.add_argument(
        "--force", action="append",
        help="allow bootstrapping even when an ADMIN already exists "
             "(pass twice to actually enforce)",
    )
    args = parser.parse_args()

    # Import AFTER argv parsing so --help works in a bare container.
    from src.auth.service import (
        audit,
        hash_password,
        password_policy_error,
    )
    from src.auth.models import AppUser
    from src.database import SessionLocal

    import os

    username = args.username.strip()
    if not username:
        print("ERROR: empty username.", file=sys.stderr)
        return 2

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    elif os_env_value("ZTD_BOOTSTRAP_PASSWORD"):
        password = os_env_value("ZTD_BOOTSTRAP_PASSWORD")
        print("Using password from ZTD_BOOTSTRAP_PASSWORD (not echoed).")
    else:
        username = _prompt_username(username)
        password = _prompt_password()

    policy = password_policy_error(password)
    if policy:
        print(f"ERROR: {policy}", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        existing_admins = (
            db.query(AppUser).filter(AppUser.role == "ADMIN").count()
        )
        force_count = len(args.force or [])
        if existing_admins > 0 and force_count < 2:
            print(
                "ERROR: an ADMIN already exists. Refusing to bootstrap.\n"
                "If you REALLY must add another admin out-of-band, pass "
                "--force --force.",
                file=sys.stderr,
            )
            return 3

        existing = (
            db.query(AppUser).filter(AppUser.username == username).one_or_none()
        )
        if existing is not None:
            # Promote/repair the existing account instead of failing.
            existing.password_hash = hash_password(password)
            existing.role = "ADMIN"
            existing.is_active = True
            target = existing
            action = "ADMIN_REPAIRED"
        else:
            target = AppUser(
                username=username,
                password_hash=hash_password(password),
                role="ADMIN",
                is_active=True,
            )
            db.add(target)
            action = "ADMIN_BOOTSTRAPPED"
        db.flush()
        audit(db, action, target=target, detail={"bootstrap": True})
        db.commit()
        print(f"OK: {action} — admin '{username}' is ready. Log in on the dashboard.")
        return 0
    finally:
        db.close()


def os_env_default(key: str, default: str) -> str:
    import os

    return os.environ.get(key, default)


def os_env_value(key: str) -> str:
    import os

    return os.environ.get(key, "")


if __name__ == "__main__":
    raise SystemExit(main())
