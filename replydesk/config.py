"""Where the keys come from. Environment first, then a file path pointed at by the environment.

Keys never live in this repository and never reach a log line. A deployment sets the environment
variable; a laptop can point at a file it keeps outside the checkout:

    TYPESAFE_API_KEY=...                  # or TYPESAFE_API_KEY_FILE=D:\\keys\\typesafe.txt
    GEMINI_API_KEY=...                    # or GEMINI_API_KEY_FILE=...
"""
from __future__ import annotations

import os
from pathlib import Path

JEV_MODEL = os.environ.get("REPLYDESK_JEV_MODEL", "jev-latest")
DRAFT_MODEL = os.environ.get("REPLYDESK_DRAFT_MODEL", "gemini-flash-lite-latest")


class MissingKey(RuntimeError):
    """Raised with the variable name to set — never with any part of a key."""


def key(name: str) -> str:
    """Read `NAME`, else the file named by `NAME_FILE`. Raises MissingKey with what to do."""
    direct = (os.environ.get(name) or "").strip()
    if direct:
        return direct
    path = (os.environ.get(f"{name}_FILE") or "").strip()
    if path:
        text = Path(path).read_text(encoding="utf-8").strip()
        if text:
            return text
        raise MissingKey(f"{name}_FILE points at an empty file: {path}")
    raise MissingKey(f"set {name}, or {name}_FILE to a file holding it")


def has(name: str) -> bool:
    try:
        key(name)
        return True
    except (MissingKey, OSError):
        return False
