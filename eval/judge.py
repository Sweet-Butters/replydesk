"""Run the judge over the frozen sample and record every answer, cost and latency.

Nothing here reads the labels. It is a separate program from the labelling on purpose: the
numbers it writes are what a person's answers are later compared against, and a script that
could see both would be a script that could be nudged.

Repeatable: `--repeat 3` asks the same question set three times per thread, which is how the
report can say whether the judge answers the same mail the same way twice.

Resumable: answers are appended to predictions.jsonl as they arrive, and a (thread, run) pair
already in the file is never paid for twice.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from replydesk import jev
from replydesk.questions import email as qs

from eval.collect import DATA as THREADS, load

OUT = Path(__file__).resolve().parent / "data" / "predictions.jsonl"


def done(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            seen.add((row["key"], row["run"]))
    return seen


def main() -> None:
    ap = argparse.ArgumentParser(description="고정된 표본에 판단 모델을 돌려 답을 기록")
    ap.add_argument("--repeat", type=int, default=1, help="스레드당 반복 횟수 (자기일관성용)")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    paths = sorted(THREADS.glob("*.json"))
    seen = done(OUT)
    todo = [(p, r) for r in range(args.repeat) for p in paths
            if (json.loads(p.read_text(encoding="utf-8"))["key"], r) not in seen]
    print(f"스레드 {len(paths)}건 × {args.repeat}회 중 {len(todo)}건 남음")

    started = time.time()
    cost = 0.0
    with OUT.open("a", encoding="utf-8") as sink:
        for i, (path, run) in enumerate(todo, 1):
            account, thread = load(path)
            key = json.loads(path.read_text(encoding="utf-8"))["key"]
            try:
                answers, usage, seconds = jev.ask(thread.as_state(), qs.QUESTIONS, args.model)
            except Exception as exc:
                print(f"  ! {key} 실패: {type(exc).__name__} {str(exc)[:120]}")
                continue
            tokens = usage.get("inputTokens") or usage.get("input_tokens") or 0
            cost += tokens / 1_000_000 * 0.042
            sink.write(json.dumps({"key": key, "account": account, "run": run,
                                   "answers": answers, "usage": usage,
                                   "seconds": seconds}, ensure_ascii=False) + "\n")
            sink.flush()
            if i % 10 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} · {time.time() - started:.0f}초 · 누적 ${cost:.4f}")
    print(f"완료 → {OUT}")


if __name__ == "__main__":
    main()
