"""Named mailboxes, so a second account is `--account work` instead of three environment variables.

The file holds paths and query strings — never a key, never a token. It lives wherever
`REPLYDESK_ACCOUNTS` points, or at `~/.replydesk/accounts.json`:

    {
      "work":     {"channel": "gmail", "email": "me@company.com",
                   "credentials": "D:/keys/client.json", "token": "D:/keys/work.json"},
      "personal": {"channel": "gmail", "email": "me@gmail.com",
                   "credentials": "D:/keys/client_personal.json", "token": "D:/keys/personal.json",
                   "query": "in:inbox -in:chats newer_than:7d"}
    }

Without the file nothing changes: the environment variables still work exactly as before.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _path() -> Path:
    return Path(os.environ.get("REPLYDESK_ACCOUNTS") or (Path.home() / ".replydesk" / "accounts.json"))


def load() -> dict:
    path = _path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 최상위가 객체여야 합니다")
    return data


def names() -> list[str]:
    return sorted(load())


def resolve(name: str) -> dict:
    """A named account's settings, with its file paths exported for the channel to pick up.

    Returns the entry; the caller reads `channel` and `email`. Setting the environment here keeps
    the channel free of any notion of "accounts" — it still only knows two paths.
    """
    entries = load()
    if name not in entries:
        raise KeyError(f"{name}: 등록되지 않은 계정입니다. 있는 것: {', '.join(names()) or '(없음)'}")
    entry = entries[name]
    for key, env in (("credentials", "GMAIL_CREDENTIALS_FILE"), ("token", "GMAIL_TOKEN_FILE")):
        if entry.get(key):
            os.environ[env] = str(Path(entry[key]).expanduser())
    return entry
