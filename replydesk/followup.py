"""The state that makes a digest answerable: what "2번" referred to this morning.

A digest is a list, and a reply to it says "2번 초안". That only means anything if the numbering
is still around when the reply arrives, so the run that sends a digest writes down which thread
each number pointed at, and the next run reads it back.

It lives in ~/.replydesk/ beside the tokens, not in the repository: it names real mail. One file,
overwritten each morning — yesterday's numbering is not something anyone should be able to act on.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


def path() -> Path:
    return Path.home() / ".replydesk" / "last_digest.json"


def save(rows: list[dict], mail: dict | None) -> Path:
    """`rows` in the order the digest numbered them; `mail` is what mail_self() returned."""
    out = path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "sent_at": dt.datetime.now().isoformat(timespec="seconds"),
        "mail": mail or {},
        "items": [{"n": i, "account": r["account"], "thread_id": r["thread_id"],
                   "subject": r["subject"], "route": r["route"]}
                  for i, r in enumerate(rows, 1)],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load() -> dict:
    p = path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def pick(state: dict, numbers: tuple[int, ...]) -> list[dict]:
    """The items a command referred to. Empty `numbers` means every item in the digest."""
    items = state.get("items", [])
    if not numbers:
        return list(items)
    by_n = {it["n"]: it for it in items}
    return [by_n[n] for n in numbers if n in by_n]


def unknown(state: dict, numbers: tuple[int, ...]) -> list[int]:
    """Numbers the digest never listed. Reported back rather than silently dropped."""
    have = {it["n"] for it in state.get("items", [])}
    return [n for n in numbers if n not in have]
