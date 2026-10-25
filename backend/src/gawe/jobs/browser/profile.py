"""Chromium profile for `access_method = browser` sources.

The profile lives outside the repo, the database, backups, and logs
(JOB-DISCOVERY.md §4.6). Gawe never reads or prints the cookies inside it: it
only starts Chromium with this directory and asks whether the session is still
usable. Deleting the directory is the only way Gawe touches a credential.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

PROFILE_DIR_NAME = "browser-profile"


def profile_dir() -> Path:
    """`%LOCALAPPDATA%\\Gawe\\browser-profile`, or `~/.gawe` off Windows."""
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".gawe"
    return base / "Gawe" / PROFILE_DIR_NAME if local else base / PROFILE_DIR_NAME


def exists() -> bool:
    return profile_dir().is_dir()


def created_at() -> float | None:
    """Directory mtime as the profile's last touch; None when absent."""
    try:
        return profile_dir().stat().st_mtime
    except OSError:
        return None


def clear() -> bool:
    """Remove the profile. Returns True when something was deleted."""
    path = profile_dir()
    if not path.is_dir():
        return False
    shutil.rmtree(path)
    return True
