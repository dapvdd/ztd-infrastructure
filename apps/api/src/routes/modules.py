import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException

from src.auth.dependencies import get_current_admin, get_current_user
from src.auth.models import AppUser

router = APIRouter(prefix="/api/v1/modules", tags=["Modules"])

MODULES_API_URL = (
    "https://api.github.com/repos/NICEganteng/modulraspipmld/"
    "contents/modules?ref=main"
)
MODULE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$")


@router.get("")
def list_available_modules(_viewer: AppUser = Depends(get_current_user)):
    """Return module directories in the public edge-agent repository.

    Sprint 5 RBAC: any authenticated dashboard session (ADMIN or VIEWER) may
    read the catalog; mutation paths are governed elsewhere.
    """
    request = Request(
        MODULES_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ztd-dashboard-module-catalog",
        },
    )

    try:
        with urlopen(request, timeout=8) as response:
            contents = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not read the module catalog from GitHub: {error}",
        ) from error

    if not isinstance(contents, list):
        raise HTTPException(
            status_code=502,
            detail="GitHub returned an invalid module catalog response.",
        )

    modules = [
        {
            "name": item["name"],
            "version": "1.0.0",
        }
        for item in contents
        if isinstance(item, dict)
        and item.get("type") == "dir"
        and isinstance(item.get("name"), str)
        and MODULE_NAME_PATTERN.fullmatch(item["name"])
    ]
    return sorted(modules, key=lambda module: module["name"])
