"""Command line: triage an inbox, or draft a reply to one thread.

    python -m replydesk triage                 # judge every waiting thread, one line each
    python -m replydesk reply t1               # judge one thread and write three drafts
    python -m replydesk reply t1 --json        # same, as JSON for another program

Nothing is sent. The drafts are printed for a person to copy, edit and send.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config
from .channels.sample import SampleChannel
from .models import Result
from .pipeline import respond, triage
from .questions import email as email_q

CHANNELS = {"sample": SampleChannel}
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
        print("\n  답장 초안 없음 (답장이 필요 없다고 판단했거나 초안 단계를 건너뜀)")
    for i, d in enumerate(result.drafts, 1):
        mark = "★" if i == 1 else " "
        print(f"\n  {mark} 후보 {i} · {d.score:.2f}")
        for para in d.text.splitlines():
            print(f"      {para}")
    tokens = result.usage.get("input_tokens", 0)
    print(f"\n  {result.seconds:.1f}초 · 판단 입력 {tokens} 토큰 · 모델 {result.usage.get('model', '')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="replydesk", description=__doc__)
    parser.add_argument("command", choices=["triage", "reply"])
    parser.add_argument("thread", nargs="?", help="thread id, for `reply`")
    parser.add_argument("--channel", default="sample", choices=sorted(CHANNELS))
    parser.add_argument("--style", default="", help="how the sender writes, one line")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    for name in ("TYPESAFE_API_KEY",) + (("GEMINI_API_KEY",) if args.command == "reply" else ()):
        if not config.has(name):
            print(f"{name} 가 없습니다. 환경변수나 {name}_FILE 로 지정하세요.", file=sys.stderr)
            return 2

    channel = CHANNELS[args.channel]()
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
                      f"{'사람이 직접' if result.answers['needs_human']['value'] >= 0.6 else '초안 가능':8} · "
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
                     style=args.style)
    if args.json:
        print(json.dumps({"id": thread.id, "answers": result.answers,
                          "drafts": [{"text": d.text, "score": d.score} for d in result.drafts],
                          "usage": result.usage}, ensure_ascii=False, indent=1))
    else:
        _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
