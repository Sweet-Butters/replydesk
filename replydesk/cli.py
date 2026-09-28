"""Command line: triage an inbox, or draft a reply to one thread.

    python -m replydesk triage                 # judge every waiting thread, one line each
    python -m replydesk reply t1               # judge one thread and write three drafts
    python -m replydesk reply t1 --json        # same, as JSON for another program
    python -m replydesk digest --channel gmail --account yonsei,personal --notify kakao

    python -m replydesk reply <id> --channel gmail --stage    # draft into the mailbox
    python -m replydesk reply <id> --channel gmail --send     # send, after showing it and asking

Sending is the only irreversible thing here, so it is the only thing that stops and asks. A model
never reaches it: `--send` is a person typing a flag, and then typing "send" at the prompt.

`digest` is the opposite direction: it writes one summary to the operator's own phone and cannot
address anyone else (see replydesk/notify).
"""
from __future__ import annotations

import argparse
import json
import sys

from . import accounts, config, digest, notify
from .channels.sample import SampleChannel
from .models import Result
from .pipeline import respond, triage
from .questions import email as email_q

def _gmail(account: str = "", query: str = ""):
    from .channels.gmail import DEFAULT_QUERY, GmailChannel   # lazily: the extra deps are optional
    return GmailChannel(account=account, query=query or DEFAULT_QUERY)


CHANNELS = {"sample": lambda account="", query="": SampleChannel(), "gmail": _gmail}
ROUTE = {"skip": "답장 불필요", "elsewhere": "폼·링크로 처리", "human": "사람이 직접",
         "draft": "초안 가능"}
BAR = "─" * 72


def _bar(value: float, width: int = 12) -> str:
    filled = max(0, min(width, round(value * width)))
    return "█" * filled + "·" * (width - filled)


def _line(qid: str, answer: dict) -> str:
    label = email_q.LABELS.get(qid, qid)
    if answer["type"] == "noul":
        return f"  {label:24} {_bar(answer['value'])} {answer['value']:.2f}"
    if answer["type"] == "choice":
        shown = email_q.INTENT_LABELS.get(answer["value"], answer["value"])
        return f"  {label:24} {_bar(answer['confidence'])} {shown} ({answer['confidence']:.2f})"
    top = max((int(k) for k in answer.get("probabilities", {"0": 1})), default=1) or 1
    return f"  {label:24} {_bar(answer['value'] / top)} {answer['value']:.1f} / {top}"


def _print_result(result: Result) -> None:
    thread = result.thread
    print(BAR)
    print(f"[{thread.id}] {thread.subject}")
    latest = thread.latest_from_them
    if latest:
        print(f"  마지막 메시지 · {latest.sender or '상대'}: {latest.text[:64]}")
    print()
    for qid, answer in result.answers.items():
        print(_line(qid, answer))
    if not result.drafts:
        why = {"skip": "답장이 필요 없다고 판단",
               "elsewhere": "답장이 아니라 폼·링크에서 처리하는 건으로 분류",
               "human": "사람이 직접 써야 하는 건으로 분류"}
        print(f"\n  초안 없음 — {why.get(email_q.route(result.answers), '초안 단계를 건너뜀')}")
    for i, d in enumerate(result.drafts, 1):
        mark = "★" if i == 1 else " "
        print(f"\n  {mark} 후보 {i} · {d.score:.2f}")
        for para in d.text.splitlines():
            print(f"      {para}")
    tokens = result.usage.get("input_tokens", 0)
    print(f"\n  {result.seconds:.1f}초 · 판단 입력 {tokens} 토큰 · 모델 {result.usage.get('model', '')}")


def confirm_send(channel, thread, result, yes: bool = False, force: bool = False) -> int:
    """Show exactly what would leave the mailbox, then require a typed word. Returns an exit code."""
    draft = result.best
    routed = email_q.route(result.answers)
    if routed != "draft" and not force:
        print(f"보내지 않았습니다 — 이 메일은 '{ROUTE[routed]}'로 분류됐습니다. "
              f"그래도 보내려면 --force 를 붙이세요.", file=sys.stderr)
        return 3
    print(BAR)
    print(f"받는 사람 : {thread.context.get('reply_to', '(알 수 없음)')}")
    print(f"제목      : {'' if thread.subject.lower().startswith('re:') else 'Re: '}{thread.subject}")
    print(f"본문      : (확신 {draft.score:.2f})")
    for line in draft.text.splitlines():
        print(f"    {line}")
    print(BAR)
    if not yes:
        if not sys.stdin.isatty():
            print("확인을 받을 수 없는 환경입니다. 직접 실행하거나 --yes 를 쓰세요.", file=sys.stderr)
            return 4
        if input("이대로 보내려면 send 를 입력하세요: ").strip().lower() != "send":
            print("보내지 않았습니다.")
            return 0
    try:
        print(f"발송 완료 → {channel.send(thread, draft.text)}")
    except (NotImplementedError, ValueError) as e:
        print(f"보내지 못했습니다: {e}", file=sys.stderr)
        return 5
    return 0


def _open(account: str, default_channel: str):
    """Build the channel for one account name (or a bare address). Returns (channel, email)."""
    email, query, channel_name = account, "", default_channel
    if account and "@" not in account:                # a name from accounts.json
        entry = accounts.resolve(account)             # exports the credential/token paths
        email, query = entry.get("email", ""), entry.get("query", "")
        channel_name = entry.get("channel", default_channel)
    return CHANNELS[channel_name](email, query), email


def _digest(args) -> int:
    """Count what a mailbox needs, in one phone-sized line, and optionally push it.

    Accounts are walked one at a time because resolving an account exports its credential paths
    into the environment — opening both first and fetching later would read one mailbox twice.
    """
    names = [n.strip() for n in args.account.split(",") if n.strip()] or [""]
    rows, failed = [], []
    for name in names:
        try:
            channel, _ = _open(name, args.channel)
            for thread in channel.fetch():
                if not thread.needs_reply:
                    continue
                answers = triage(thread, email_q.QUESTIONS).answers
                rows.append({"account": name or args.channel, "subject": thread.subject,
                             "route": email_q.route(answers),
                             "urgency": answers.get("urgency", {}).get("value", 0.0)})
        except Exception as exc:                      # one unreachable mailbox must not lose the rest
            failed.append(f"{name or args.channel}: {type(exc).__name__} {str(exc)[:80]}")

    text = digest.summarize(rows)
    print(text)
    for line in failed:
        print(f"(읽지 못한 메일함 — {line})", file=sys.stderr)
    if args.notify:
        try:
            print(f"\n{notify.send(args.notify, text)}")
        except (RuntimeError, OSError, config.MissingKey) as exc:
            print(f"알림을 보내지 못했습니다: {exc}", file=sys.stderr)
            return 5
    return 1 if failed and not rows else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="replydesk", description=__doc__)
    parser.add_argument("command", choices=["triage", "reply", "digest"])
    parser.add_argument("thread", nargs="?", help="thread id, for `reply`")
    parser.add_argument("--channel", default="sample", choices=sorted(CHANNELS))
    parser.add_argument("--account", default="",
                        help="a name from accounts.json, or an email address; "
                             "digest 에서는 쉼표로 여러 개")
    parser.add_argument("--stage", action="store_true",
                        help="put the top draft where the person sends it (Gmail: a draft)")
    parser.add_argument("--send", action="store_true",
                        help="send the top draft after showing it and asking for confirmation")
    parser.add_argument("--yes", action="store_true",
                        help="answer the send confirmation in advance (for a supervised script)")
    parser.add_argument("--force", action="store_true",
                        help="allow sending a thread the judge routed to a person")
    parser.add_argument("--style", default="", help="how the sender writes, one line")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--notify", default="", choices=sorted(notify.NOTIFIERS),
                        help="digest 결과를 보낼 곳 (kakao: 카카오톡 '나와의 채팅')")
    args = parser.parse_args(argv)

    for name in ("TYPESAFE_API_KEY",) + (("GEMINI_API_KEY",) if args.command == "reply" else ()):
        if not config.has(name):
            print(f"{name} 가 없습니다. 환경변수나 {name}_FILE 로 지정하세요.", file=sys.stderr)
            return 2

    if args.command == "digest":
        return _digest(args)          # its own path: it walks several mailboxes, not one

    try:
        channel, email = _open(args.account, args.channel)
    except (KeyError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    threads = [t for t in channel.fetch() if t.needs_reply]

    if args.command == "triage":
        rows = []
        for thread in threads:
            result = triage(thread, email_q.QUESTIONS)
            rows.append(result)
            if not args.json:
                intent = result.answers["intent"]
                print(f"[{thread.id}] 긴급 {result.answers['urgency']['value']:.1f}/3 · "
                      f"{email_q.INTENT_LABELS.get(intent['value'], intent['value']):8} · "
                      f"{ROUTE[email_q.route(result.answers)]:8} · "
                      f"{thread.subject[:38]}")
        if args.json:
            print(json.dumps([{"id": r.thread.id, "answers": r.answers} for r in rows],
                             ensure_ascii=False, indent=1))
        return 0

    if not args.thread:
        parser.error("reply 는 thread id 가 필요합니다")
    thread = next((t for t in channel.fetch() if t.id == args.thread), None)
    if thread is None:
        print(f"{args.thread} 스레드를 찾지 못했습니다", file=sys.stderr)
        return 1
    result = respond(thread, email_q.QUESTIONS, email_q.guidance, email_q.RANK_INSTRUCTIONS,
                     style=args.style, route=email_q.route,
                     claim_check=email_q.UNSUPPORTED_CLAIM,
                     claim_limit=email_q.THRESHOLDS["unsupported_claim"])
    if args.send and result.best:
        code = confirm_send(channel, thread, result, yes=args.yes, force=args.force)
        if code:
            return code
    elif args.stage and result.best:
        try:
            print(f"초안을 넣었습니다 → {channel.stage(thread, result.best.text)}")
        except NotImplementedError as e:
            print(f"이 채널은 초안을 넣을 수 없습니다: {e}", file=sys.stderr)
    if args.json:
        print(json.dumps({"id": thread.id, "answers": result.answers,
                          "drafts": [{"text": d.text, "score": d.score} for d in result.drafts],
                          "usage": result.usage}, ensure_ascii=False, indent=1))
    else:
        _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
