"""The other direction: a reply to the digest, read back as an instruction.

KakaoTalk's note-to-self is one-way — nothing can read what you type there — so the digest can
tell you what needs answering but you cannot answer *it*. Mail can. The digest is also sent to
your own address with the threads numbered, and replying to it with "2번 초안" is an instruction
the next run picks up. No new service, no webhook, no open port: the mailbox this tool already
reads is the inbox and the command channel at once.

Two rules make that safe to do:

  * Only mail **from the account holder, in a thread this program started** is ever parsed as a
    command. A stranger cannot mail you an instruction, because their message is not a reply to
    a digest we sent. Anything else is ordinary correspondence and gets judged, not obeyed.
  * The verbs are a closed set, and none of them sends anything. The strongest thing a command
    can do is put a draft in your own drafts folder.

Grammar, deliberately small enough to type with a thumb:

    2번 초안        3 draft          draft 3      → write drafts for thread 3
    2번 건너뛰기     3 skip                        → mark it handled, drop it from tomorrow
    2, 5번 초안     2,5 draft                     → several at once
    전체 건너뛰기    all skip                      → clear the list
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# What a digest reply may ask for. Nothing here sends mail; `draft` stages into the drafts folder.
VERBS = {
    "draft": ("초안", "draft", "쓰기", "작성", "답장써"),
    "skip": ("건너", "skip", "무시", "패스", "넘기"),
}
ALL = ("전체", "모두", "all", "다")

_NUMBERS = re.compile(r"(\d+)\s*(?:번|번째|\.)?")
_QUOTED = re.compile(r"^\s*(?:>|On .*wrote:|\d{4}년 .*작성:)", re.M)


@dataclass(frozen=True)
class Command:
    verb: str                 # "draft" | "skip"
    numbers: tuple[int, ...]  # 1-based positions from the digest; empty means every listed thread
    source: str               # the line it came from, for the reply that confirms what was done

    @property
    def everything(self) -> bool:
        return not self.numbers


def _first_lines(text: str, keep: int = 6) -> list[str]:
    """The part the person typed. A phone puts the quoted digest right underneath it."""
    cut = _QUOTED.search(text)
    if cut:
        text = text[:cut.start()]
    return [line.strip() for line in text.splitlines() if line.strip()][:keep]


def parse(text: str) -> list[Command]:
    """Read instructions out of a digest reply. Unrecognised lines are ignored, never guessed at.

    Ignoring is the right failure: a line this does not understand means the person gets a reply
    saying so, which is recoverable. Guessing means acting on something they did not ask for.
    """
    out: list[Command] = []
    for line in _first_lines(text):
        verb = next((name for name, words in VERBS.items()
                     if any(w in line.lower() for w in words)), "")
        if not verb:
            continue
        if any(word in line.lower() for word in ALL) and not _NUMBERS.search(line):
            out.append(Command(verb, (), line))
            continue
        numbers = tuple(dict.fromkeys(int(n) for n in _NUMBERS.findall(line) if 0 < int(n) < 1000))
        if numbers:
            out.append(Command(verb, numbers, line))
        elif any(word in line.lower() for word in ALL):
            out.append(Command(verb, (), line))
    return out


def describe(commands: list[Command]) -> str:
    """What we understood, in the person's words, so a misread is visible before anything happens."""
    if not commands:
        return "알아들은 지시가 없습니다."
    parts = []
    for c in commands:
        what = "초안 작성" if c.verb == "draft" else "건너뛰기"
        where = "전체" if c.everything else ", ".join(f"{n}번" for n in c.numbers)
        parts.append(f"{where} → {what}")
    return " / ".join(parts)
