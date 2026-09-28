"""The digest is what lands on a phone, so its budget is tested, not trusted.

No network: `summarize` is a pure function, and the notifier registry is checked by name only.
"""
from __future__ import annotations

import datetime as dt

import pytest

from replydesk import digest, notify

DAY = dt.date(2026, 9, 29)


def row(subject: str, route: str = "draft", urgency: float = 1.0) -> dict:
    return {"account": "work", "subject": subject, "route": route, "urgency": urgency}


def test_counts_only_the_routes_that_occur():
    text = digest.summarize([row("a"), row("b", "elsewhere"), row("c", "skip")], DAY)
    assert "메일 3건" in text
    assert "답장 1" in text and "폼·링크 1" in text
    assert "불필요" not in text              # a count of zero is noise on a phone


def test_says_so_when_nothing_needs_an_answer():
    text = digest.summarize([row("a", "skip"), row("b", "skip")], DAY)
    assert "답장이 필요한 메일은 없습니다" in text
    assert text.count("\n") == 1             # header + that line, no empty bullet list


def test_only_actionable_threads_are_named():
    text = digest.summarize([row("초안 대상"), row("폼에서 처리", "elsewhere"),
                             row("건너뜀", "skip")], DAY)
    assert "초안 대상" in text
    assert "폼에서 처리" not in text          # counted, not named: there is nothing to write
    assert "건너뜀" not in text


def test_most_urgent_is_named_first_and_marked():
    text = digest.summarize([row("느긋한 건", urgency=0.2), row("급한 건", urgency=2.9)], DAY)
    lines = text.splitlines()
    assert "급한 건" in lines[2] and lines[2].startswith("🔴")
    assert "느긋한 건" in lines[3] and not lines[3].startswith("🔴")


def test_never_exceeds_the_kakao_limit_and_says_how_many_were_dropped():
    rows = [row(f"아주 긴 제목을 가진 메일 번호 {i} " + "가" * 30, urgency=3 - i * 0.01)
            for i in range(20)]
    text = digest.summarize(rows, DAY)
    assert len(text) <= 200
    assert "외" in text.splitlines()[-1]      # the rest is acknowledged, not silently missing


def test_long_subject_is_clipped_not_wrapped():
    text = digest.summarize([row("제목" * 60)], DAY)
    assert len(text) <= 200
    assert text.rstrip().endswith("…")
    assert len(text.splitlines()) == 3


def test_unknown_notifier_names_the_ones_that_exist():
    with pytest.raises(RuntimeError) as err:
        notify.send("sms", "안녕")
    assert "kakao" in str(err.value)


def test_kakao_truncates_before_sending(monkeypatch):
    """The API silently drops anything past 200 characters; we cut it visibly instead."""
    from replydesk.notify import kakao

    sent = {}
    monkeypatch.setattr(kakao, "_access_token", lambda: "test-token")
    monkeypatch.setattr(kakao, "_post", lambda url, form, headers=None: sent.update(form) or {})
    kakao.send("가" * 400)
    import json
    body = json.loads(sent["template_object"])["text"]
    assert len(body) == kakao.LIMIT and body.endswith("…")
