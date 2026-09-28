"""One short line about a whole mailbox, small enough to read on a phone.

The judge already decides what each thread needs; a digest only says how many of each and names
the ones a person has to act on. It is built as a pure function so the wording can be tested
without a mailbox or a network.

The length cap is real: KakaoTalk's note-to-self template keeps 200 characters and silently drops
the rest, so the budget is spent deliberately — counts first, then as many subjects as fit, most
urgent first.
"""
from __future__ import annotations

import datetime as dt

ROUTE_SHORT = {"draft": "답장", "elsewhere": "폼·링크", "human": "직접", "skip": "불필요"}
ACT = ("draft", "human")          # the two that need the person; "elsewhere" is a link to click


def _clip(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def summarize(rows: list[dict], today: dt.date | None = None, limit: int = 200) -> str:
    """`rows`: {"subject", "route", "urgency", "account"}. Returns the message body."""
    day = (today or dt.date.today()).strftime("%m/%d").lstrip("0")
    counts = {k: sum(1 for r in rows if r["route"] == k) for k in ROUTE_SHORT}
    head = f"[replydesk] {day} 메일 {len(rows)}건"
    tally = " · ".join(f"{ROUTE_SHORT[k]} {counts[k]}" for k in ("draft", "elsewhere", "human")
                       if counts[k])
    lines = [head, tally or "답장이 필요한 메일은 없습니다"]

    todo = sorted((r for r in rows if r["route"] in ACT),
                  key=lambda r: -float(r.get("urgency") or 0))
    used = len("\n".join(lines))
    for i, row in enumerate(todo):
        left = len(todo) - i
        tail = f"…외 {left}건"
        # The overflow line has to fit too. Budgeting for it only after filling the space is how
        # the count of what was dropped gets dropped — the one line that must never be cut.
        room = limit - used - 3 - (len(tail) + 1)      # newline + marker + space, then the tail
        if room < 12:                                  # too little left to name anything usefully
            lines.append(tail)
            break
        line = f"{mark_for(row)} {_clip(row['subject'], min(room, 42))}"
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def mark_for(row: dict) -> str:
    return "🔴" if float(row.get("urgency") or 0) >= 2.5 else "·"
