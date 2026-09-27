"""What a channel has to provide. Everything above this line is channel-agnostic.

A channel reads threads and, optionally, puts a chosen draft where the person can send it — into
the mail client's reply box, a ticket's draft field, a clipboard. Nothing in this project sends on
anyone's behalf: `stage` is the last step a machine takes.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import Thread


@runtime_checkable
class Channel(Protocol):
    name: str

    def fetch(self, limit: int = 20) -> list[Thread]:
        """Threads waiting on us, newest first."""

    def stage(self, thread: Thread, text: str) -> str:
        """Put `text` where the person will review and send it. Returns a human-readable location.

        A channel that cannot stage raises NotImplementedError; the caller falls back to printing.
        """
