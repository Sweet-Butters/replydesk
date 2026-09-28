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


def listed(rows: list[dict]) -> list[dict]:
    """The rows worth numbering: everything except the ones nothing has to happen to.

    Numbering all forty would make "2번" point at a newsletter and bury the three lines that
    matter. The skipped mail is counted in the header instead — it is still visible, just not
    addressable.
    """
    return [r for r in rows if r["route"] != "skip"]


def as_mail(rows: list[dict], today: dt.date | None = None, total: int | None = None) -> tuple[str, str]:
    """The same digest as an email: numbered, with the grammar for answering it at the bottom.

    Mail has no 200-character budget and, unlike the KakaoTalk room, it can be replied to — so
    every thread that needs anything gets a number the reply can name. `rows` should already be
    `listed(...)`; `total` is how many were judged in all. Returns (subject, body).
    """
    day = (today or dt.date.today()).strftime("%m/%d").lstrip("0")
    counts = {k: sum(1 for r in rows if r["route"] == k) for k in ROUTE_SHORT}
    judged = len(rows) if total is None else total
    subject = f"[replydesk] {day} 받은편지함 {judged}건 · 답장 {counts['draft']}"
    lines = [f"{day} 기준 {judged}건을 판단했고, 손댈 것은 {len(rows)}건입니다.", ""]
    if not rows:
        lines.append("답장이 필요한 메일은 없습니다.")
    for i, row in enumerate(rows, 1):
        urgency = float(row.get("urgency") or 0)
        mark = "[급함] " if urgency >= 2.5 else ""
        lines.append(f"{i:2d}. {mark}{ROUTE_SHORT[row['route']]} · {_clip(row['subject'], 60)}")
        lines.append(f"      {row['account']} · 긴급도 {urgency:.1f}/3")
    if total is not None and total > len(rows):
        lines += ["", f"(나머지 {total - len(rows)}건은 답장 불필요로 판단해 목록에서 뺐습니다)"]
    lines += [
        "",
        "─" * 46,
        "이 메일에 답장해서 시킬 수 있습니다 (맨 윗줄에 쓰세요):",
        "",
        "  2번 초안          → 2번 메일의 답장 초안을 임시보관함에 넣습니다",
        "  2, 5번 초안       → 여러 건을 한 번에",
        "  3번 건너뛰기      → 처리한 것으로 표시하고 다음 요약에서 뺍니다",
        "  전체 건너뛰기     → 목록을 비웁니다",
        "",
        "초안까지만 합니다. 발송은 이 경로로 되지 않습니다.",
    ]
    return subject, "\n".join(lines)
