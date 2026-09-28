"""judge → write → rank, for any channel.

The order matters: the judgement is what makes the drafts specific, and ranking after writing is
the only point where Jev sees the actual candidates. Skipping the middle step is supported — a
triage run that only judges costs one call and is what you want when sorting an inbox.
"""
from __future__ import annotations

import time

from . import draft as writer
from . import jev
from .models import Draft, Result, Thread


def _merge(total: dict, one: dict) -> None:
    for k, v in (one or {}).items():
        total[k] = total.get(k, 0) + v if isinstance(v, (int, float)) else v


def triage(thread: Thread, questions: dict, keep: int = 12) -> Result:
    """One Jev call: every question, no drafting. Cheap enough to run over a whole inbox."""
    answers, usage, seconds = jev.ask(thread.as_state(keep), questions)
    return Result(thread=thread, answers=answers, usage=usage, seconds=seconds)


def respond(thread: Thread, questions: dict, guidance, rank_instructions: str,
            style: str = "", keep: int = 12, drafts: int = 3, route=None,
            claim_check: str = "", claim_limit: float = 0.5) -> Result:
    """Full pass. `guidance` turns the answers into the note the writer follows.

    `route(answers) -> "skip" | "human" | "draft"` decides whether to write at all; pass the
    channel's own (see questions/email.route). Without one, every thread gets drafts.
    """
    started = time.perf_counter()
    state = thread.as_state(keep)
    answers, usage, _ = jev.ask(state, questions)
    total: dict = {}
    _merge(total, usage)
    if route and route(answers) != "draft":
        # "skip" (no reply expected) and "human" (too sensitive to hand someone a draft) both stop
        # here: the caller still gets the judgement and can show why nothing was written.
        return Result(thread=thread, answers=answers, usage=total, seconds=time.perf_counter() - started)

    texts, draft_usage, _ = writer.write(state, guidance(answers), style)
    total["draft_input_tokens"] = draft_usage.get("input_tokens", 0)
    total["draft_output_tokens"] = draft_usage.get("output_tokens", 0)
    texts = texts[:drafts]
    if claim_check and texts:
        # The writer invents; the judge catches it. Keep the least-inventing one if all fail, so a
        # person still has something to edit, and let the score show why it is the only option.
        claims, claim_usage = jev.check(state, texts, claim_check)
        _merge(total, claim_usage)
        kept = [t for t, c in zip(texts, claims) if c < claim_limit]
        texts = kept or [min(zip(texts, claims), key=lambda pair: pair[1])[0]]
    scores, rank_usage = jev.rank(state, texts, rank_instructions)
    _merge(total, rank_usage)
    ranked = tuple(sorted((Draft(text=t, score=s) for t, s in zip(texts, scores)),
                          key=lambda d: -d.score))
    return Result(thread=thread, answers=answers, drafts=ranked, usage=total,
                  seconds=time.perf_counter() - started)
