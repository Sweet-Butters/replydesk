"""The judge: TypeSafe's Jev answers typed questions about a thread and ranks our drafts.

Jev returns a value plus a probability distribution, which is the whole reason it sits here instead
of a chat model: `intent == "refund"` with confidence 0.93 is something code can branch on, and a
low confidence is something code can route to a human. It never writes the reply.
"""
from __future__ import annotations

import time
from typing import Any

from typesafe_sdk import TypeSafeClient

from . import config

_client: TypeSafeClient | None = None


def client() -> TypeSafeClient:
    global _client
    if _client is None:
        _client = TypeSafeClient(api_key=config.key("TYPESAFE_API_KEY"))
    return _client


def normalize(answer: Any) -> dict:
    """SDK answer -> plain dict. `value` is what code should branch on, whatever the question type.

    noul has no confidence of its own: how far the probability sits from 0.5 is the certainty,
    so we report that on the same 0..1 scale as the other two and never invent one.
    """
    kind = getattr(answer, "type", None) or (answer.get("type") if isinstance(answer, dict) else None)
    get = (lambda k, d=None: getattr(answer, k, d)) if not isinstance(answer, dict) else answer.get
    if kind == "noul":
        p = float(get("noul"))
        return {"type": "noul", "value": p, "confidence": abs(p - 0.5) * 2}
    if kind == "choice":
        return {"type": "choice", "value": get("choice"), "confidence": float(get("confidence", 0.0)),
                "probabilities": dict(get("probabilities", {}) or {})}
    if kind == "score":
        return {"type": "score", "value": float(get("score")), "confidence": float(get("confidence", 0.0)),
                "legend": dict(get("legend", {}) or {}), "probabilities": dict(get("probabilities", {}) or {})}
    raise ValueError(f"unknown answer type: {kind!r}")


def ask(state: Any, questions: dict, model: str | None = None) -> tuple[dict, dict, float]:
    """Ask every question in one call — Jev reads the state once and answers them in parallel,
    so a question you might not need costs a few tokens, not a round trip.

    Returns (answers, usage, seconds).
    """
    started = time.perf_counter()
    response = client().system_one(state=state, questions=questions, model=model or config.JEV_MODEL)
    answers = {qid: normalize(a) for qid, a in response.answers.items()}
    usage = {"input_tokens": getattr(response.usage, "input_tokens", 0),
             "output_tokens": getattr(response.usage, "output_tokens", 0),
             "model": getattr(response, "model", "")}
    return answers, usage, time.perf_counter() - started


def check(state: Any, drafts: list[str], question: str, model: str | None = None) -> tuple[list[float], dict]:
    """Ask one yes/no question about each draft, in a single call.

    The draft travels inside the question rather than the state: the state is the thread, and a
    draft is not part of it. Returns one probability per draft, in order.
    """
    if not drafts:
        return [], {}
    questions = {f"d{i}": {"type": "noul", "instructions": {"draft": text, "question": question}}
                 for i, text in enumerate(drafts)}
    answers, usage, _ = ask(state, questions, model=model)
    return [answers[f"d{i}"]["value"] for i in range(len(drafts))], usage


def rank(state: Any, drafts: list[str], instructions: str, model: str | None = None) -> tuple[list[float], dict]:
    """Score each draft as "the one to send". Returns probabilities in the drafts' order.

    One Choice over the drafts, rather than one Noul each: the options compete for one distribution,
    which is what "pick one" means. A single draft needs no call.
    """
    if len(drafts) < 2:
        return [1.0] * len(drafts), {}
    keys = [f"d{i}" for i in range(len(drafts))]
    question = {"type": "choice", "instructions": instructions,
                "criteria": {k: text for k, text in zip(keys, drafts)}}
    answers, usage, _ = ask(state, {"best": question}, model=model)
    probs = answers["best"].get("probabilities", {})
    return [float(probs.get(k, 0.0)) for k in keys], usage
