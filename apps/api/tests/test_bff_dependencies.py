"""F-04 regression: BFF session dependencies must be declared.

The staging runtime check hit POST /api/dashboard/session -> 500 with
ModuleNotFoundError: No module named 'itsdangerous'. The BFF lazily imports
it inside _signer(), so no test failed until login ran in a real container.
"""

import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def test_itsdangerous_declared():
    with open(os.path.join(REPO, "apps", "api", "requirements.txt"), encoding="utf-8") as fh:
        reqs = fh.read()
    assert "itsdangerous" in reqs, (
        "dashboard_bff._signer lazily imports itsdangerous; it must be in "
        "requirements.txt or login 500s in the deployed container"
    )


def test_bff_imports_are_covered():
    """Every module imported inside dashboard_bff must be stdlib or declared."""
    import ast

    bff_path = os.path.join(REPO, "apps", "api", "src", "routes", "dashboard_bff.py")
    with open(bff_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    with open(os.path.join(REPO, "apps", "api", "requirements.txt"), encoding="utf-8") as fh:
        reqs = fh.read()

    declared = {"fastapi", "uvicorn", "pydantic_settings", "psycopg2", "sqlalchemy",
                "paramiko", "paho", "itsdangerous", "pydantic"}
    # stdlib modules used by dashboard_bff
    stdlib = {"__future__", "base64", "hashlib", "hmac", "os", "secrets", "time",
              "typing", "urllib"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    for mod in sorted(imported):
        if mod in ("src",) or mod in declared or mod in stdlib:
            continue
        # Third-party unknown import: flag it
        assert mod in declared, (
            f"dashboard_bff imports '{mod}' which is not in requirements.txt "
            "and not a known declared dependency"
        )
