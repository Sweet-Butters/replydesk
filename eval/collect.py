"""Pull real threads out of the connected mailboxes and park them on disk.

Measuring judgement accuracy needs the same threads twice: once for a person to label, once
for the judge to answer. Fetching them twice would be two mailbox reads of the same mail and
two chances to disagree about what the input was, so the input is frozen here first.

Resumable on purpose. A full thread read costs ~10 quota units against a per-minute budget, so
a mailbox scan trips "Quota exceeded" partway through; every thread is written the moment it
arrives and an already-written thread is never fetched again.

The files hold real correspondence. They live in eval/data/, which the repository ignores.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from replydesk import accounts
from replydesk.channels.gmail import GmailChannel
from replydesk.models import Message, Thread

DATA = Path(__file__).resolve().parent / "data" / "threads"
PAUSE = 1.5        # seconds between thread reads; keeps us under the per-minute budget
QUERY = "in:inbox -in:chats newer_than:120d"


def dump(thread: Thread, account: str) -> dict:
    return {
        "key": f"{account}:{thread.id}",
        "account": account,
        "id": thread.id,
        "channel": thread.channel,
        "subject": thread.subject,
        "context": thread.context,
        "messages": [{"side": m.side, "text": m.text, "sender": m.sender,
                      "at": m.at.isoformat() if m.at else None,
                      "attachments": list(m.attachments)} for m in thread.messages],
    }


def load(path: Path) -> tuple[str, Thread]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    import datetime as dt
    messages = tuple(Message(side=m["side"], text=m["text"], sender=m["sender"],
                             at=dt.datetime.fromisoformat(m["at"]) if m["at"] else None,
                             attachments=tuple(m["attachments"])) for m in raw["messages"])
    return raw["account"], Thread(id=raw["id"], channel=raw["channel"], subject=raw["subject"],
                                  messages=messages, context=raw["context"])


def stored() -> list[tuple[str, Thread]]:
    return [load(p) for p in sorted(DATA.glob("*.json"))]


def collect(account: str, want: int, scan: int, query: str = QUERY) -> int:
    """Fetch up to `want` unseen threads from one mailbox. Returns how many are new."""
    from replydesk.channels.gmail import _call

    entry = accounts.resolve(account)
    channel = GmailChannel(account=entry["email"], query=query)
    DATA.mkdir(parents=True, exist_ok=True)
    listed = _call(channel.service.users().threads().list(
        userId="me", q=channel.query, maxResults=scan))
    new = 0
    for ref in listed.get("threads", [])[:scan]:
        path = DATA / f"{account}-{ref['id']}.json"
        if path.exists():
            continue                      # already frozen; never spend quota on it twice
        if new >= want:
            break
        raw = _call(channel.service.users().threads().get(
            userId="me", id=ref["id"], format="full"))
        thread = channel._to_thread(raw)
        time.sleep(PAUSE)
        if not thread or not thread.needs_reply:
            continue                      # the population the pipeline judges: mail waiting on us
        path.write_text(json.dumps(dump(thread, account), ensure_ascii=False, indent=1),
                        encoding="utf-8")
        new += 1
        print(f"  + {account}: {thread.subject[:50]!r} ({len(thread.messages)}통)")
    return new


def replied(account: str, want: int, scan: int, days: int = 365) -> int:
    """Threads the person actually answered, rewound to the moment before they did.

    An inbox scan is almost all announcements, so the "a reply is needed" side of the sample ends
    up too thin to measure. Mail that was in fact replied to supplies that side without anyone
    guessing: cut the thread at the last message from the other party and the judge faces exactly
    the decision the person already made. Their answer — they wrote back — is the label.
    """
    from replydesk.channels.gmail import _call

    entry = accounts.resolve(account)
    query = f"from:me -in:chats newer_than:{days}d"
    channel = GmailChannel(account=entry["email"], query=query)
    DATA.mkdir(parents=True, exist_ok=True)
    listed = _call(channel.service.users().threads().list(
        userId="me", q=query, maxResults=scan))
    new = 0
    for ref in listed.get("threads", [])[:scan]:
        path = DATA / f"{account}-{ref['id']}.json"
        if path.exists():
            continue
        if new >= want:
            break
        raw = _call(channel.service.users().threads().get(
            userId="me", id=ref["id"], format="full"))
        thread = channel._to_thread(raw)
        time.sleep(PAUSE)
        if not thread:
            continue
        sides = [m.side for m in thread.messages]
        if "us" not in sides or "them" not in sides:
            continue
        end = len(sides) - 1 - sides[::-1].index("them")   # last message from the other party
        if end == len(sides) - 1:
            continue                                        # never answered: not a positive
        cut = Thread(id=thread.id, channel=thread.channel, subject=thread.subject,
                     messages=thread.messages[:end + 1], context=thread.context)
        record = dump(cut, account)
        record["replied_later"] = True                       # behavioural label, not a guess
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        new += 1
        print(f"  + {account}: [답장함] {cut.subject[:44]!r} ({len(cut.messages)}통)")
    return new


def main() -> None:
    ap = argparse.ArgumentParser(description="실제 메일을 평가용으로 고정 저장")
    ap.add_argument("--account", action="append", default=None)
    ap.add_argument("--want", type=int, default=25, help="계정당 새로 받을 스레드 수")
    ap.add_argument("--scan", type=int, default=120, help="계정당 열어볼 스레드 상한")
    ap.add_argument("--query", default=QUERY)
    ap.add_argument("--replied", action="store_true",
                    help="실제로 답장한 스레드를 답장 직전 시점으로 잘라서 수집")
    args = ap.parse_args()

    for name in args.account or ["yonsei", "personal"]:
        try:
            new = (replied(name, args.want, args.scan) if args.replied
                   else collect(name, args.want, args.scan, args.query))
            print(f"{name}: 새로 {new}건")
        except Exception as exc:                      # quota, token, network — keep what we have
            print(f"{name}: 중단됨 ({type(exc).__name__}) — 이미 받은 건은 남아 있습니다")
            print(f"  {str(exc)[:200]}")
    print(f"총 저장 {len(list(DATA.glob('*.json')))}건 → {DATA}")


if __name__ == "__main__":
    main()
