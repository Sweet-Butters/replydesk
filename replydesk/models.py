"""What every channel boils down to: a thread of messages, and who wrote each one.

An email thread, a KakaoTalk room and a CS ticket differ in transport, not in shape — so the
pipeline only ever sees this. A channel adapter's whole job is to produce these.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

Side = Literal["them", "us"]


@dataclass(frozen=True)
class Message:
    side: Side
    text: str
    sender: str = ""              # display name; "" when the channel has none
    at: dt.datetime | None = None
    attachments: tuple[str, ...] = ()

    def as_state(self) -> dict:
        """One line of the state handed to the judge. Keys stay short: they are billed as tokens."""
        out: dict = {"from": self.sender or self.side, "text": self.text}
        if self.at:
            out["at"] = self.at.isoformat(timespec="minutes")
        if self.attachments:
            out["attachments"] = list(self.attachments)
        return out


@dataclass(frozen=True)
class Thread:
    id: str
    channel: str                  # "email", "kakaotalk", "cs", ...
    subject: str = ""
    messages: tuple[Message, ...] = ()
    context: dict = field(default_factory=dict)   # channel facts: order status, plan, SLA, ...

    @property
    def latest_from_them(self) -> Message | None:
        return next((m for m in reversed(self.messages) if m.side == "them"), None)

    @property
    def needs_reply(self) -> bool:
        """Nothing to draft when we spoke last — the ball is not in our court."""
        return bool(self.messages) and self.messages[-1].side == "them"

    def as_state(self, keep: int = 12) -> dict:
        """The judge sees the thread plus whatever the channel knows; never raw HTML or headers."""
        state: dict = {"channel": self.channel,
                       "thread": [m.as_state() for m in self.messages[-keep:]]}
        if self.subject:
            state["subject"] = self.subject
        if self.context:
            state["context"] = self.context
        return state


@dataclass(frozen=True)
class Draft:
    text: str
    score: float = 0.0            # Jev's probability that this is the one to send
    rationale: str = ""


@dataclass(frozen=True)
class Result:
    thread: Thread
    answers: dict                 # question id -> typed answer, straight from Jev
    drafts: tuple[Draft, ...] = ()
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def best(self) -> Draft | None:
        return max(self.drafts, key=lambda d: d.score, default=None)
