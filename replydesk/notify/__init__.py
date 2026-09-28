"""Where a finished judgement goes so a person actually sees it.

A notifier is not a channel. A channel reads other people's messages and can answer them; a
notifier writes one line to the operator and nothing else. Keeping them in separate packages is
what makes "the summary goes to my phone" a small feature instead of a new way to mail a stranger
by accident.

Every notifier is one function: `send(text) -> str`, raising RuntimeError with what to fix.
"""
from __future__ import annotations

from typing import Callable

NOTIFIERS: dict[str, Callable[[str], str]] = {}


def _kakao(text: str) -> str:
    from . import kakao            # imported late: no key or token is touched until it is used
    return kakao.send(text)


NOTIFIERS["kakao"] = _kakao


def send(where: str, text: str) -> str:
    if where not in NOTIFIERS:
        raise RuntimeError(f"{where}: 모르는 알림 대상입니다. 있는 것: {', '.join(sorted(NOTIFIERS))}")
    return NOTIFIERS[where](text)
