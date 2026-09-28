"""The command channel is the one place a mailbox tells the program what to do.

So the tests are mostly about what it must *refuse* to understand. Ordinary mail has to stay
ordinary mail, and a line nobody wrote on purpose must not turn into an action.
"""
from __future__ import annotations

import datetime as dt

from replydesk import commands, digest, followup

DAY = dt.date(2026, 9, 29)


def row(subject: str, route: str = "draft", urgency: float = 1.0, tid: str = "t1") -> dict:
    return {"account": "work", "subject": subject, "route": route,
            "urgency": urgency, "thread_id": tid}


def test_reads_the_two_verbs_in_both_languages():
    assert commands.parse("2번 초안")[0] == commands.Command("draft", (2,), "2번 초안")
    assert commands.parse("draft 3")[0].verb == "draft"
    assert commands.parse("3번 건너뛰기")[0].verb == "skip"
    assert commands.parse("5 skip")[0].numbers == (5,)


def test_several_numbers_in_one_line_keep_their_order_once():
    cmd = commands.parse("2, 5, 2번 초안")[0]
    assert cmd.numbers == (2, 5)


def test_all_means_every_listed_thread():
    cmd = commands.parse("전체 건너뛰기")[0]
    assert cmd.everything and cmd.verb == "skip"


def test_ordinary_mail_is_not_a_command():
    for text in ("안녕하세요, 회의 일정 관련해서 문의드립니다.",
                 "Thanks! Talk soon.",
                 "3일까지 검토 부탁드립니다."):      # a number, but no verb
        assert commands.parse(text) == []


def test_the_quoted_digest_underneath_is_not_re_read():
    """A phone reply carries the whole digest below it — and that digest lists numbers."""
    text = ("2번 초안\n\n"
            "2026년 9월 29일 작성:\n"
            "> 1. 답장 · 견적서 회신 부탁드립니다\n"
            "> 3. 답장 · 초안 작성 요청\n"
            "> 5번 초안\n")
    cmds = commands.parse(text)
    assert len(cmds) == 1 and cmds[0].numbers == (2,)


def test_a_bare_number_without_a_verb_does_nothing():
    assert commands.parse("2번") == []
    assert commands.parse("2") == []


def test_describe_shows_what_was_understood():
    said = commands.describe(commands.parse("2, 5번 초안\n3번 건너뛰기"))
    assert "2번, 5번 → 초안 작성" in said and "3번 → 건너뛰기" in said


def test_mail_numbers_every_actionable_row_and_explains_the_grammar():
    subject, body = digest.as_mail([row("첫째"), row("둘째", "elsewhere")], DAY)
    assert "9/29" in subject and "2건" in subject
    assert " 1. " in body and " 2. " in body      # elsewhere is numbered too: it can be skipped
    assert "2번 초안" in body and "전체 건너뛰기" in body
    assert "발송은 이 경로로 되지 않습니다" in body


def test_mail_leaves_out_what_needs_nothing_but_still_counts_it():
    """Numbering forty newsletters would make "2번" point at one of them."""
    rows = [row("답장할 것"), row("공지 1", "skip"), row("공지 2", "skip")]
    shown = digest.listed(rows)
    assert [r["subject"] for r in shown] == ["답장할 것"]
    _, body = digest.as_mail(shown, DAY, total=len(rows))
    assert "공지" not in body
    assert "나머지 2건" in body                    # counted, not hidden
    assert "3건을 판단했고, 손댈 것은 1건" in body


def test_mail_marks_the_urgent_ones():
    _, body = digest.as_mail([row("급한 건", urgency=2.9)], DAY)
    assert "[급함]" in body


def test_pick_maps_numbers_back_to_threads():
    state = {"items": [{"n": 1, "thread_id": "a"}, {"n": 2, "thread_id": "b"}]}
    assert [it["thread_id"] for it in followup.pick(state, (2,))] == ["b"]
    assert len(followup.pick(state, ())) == 2         # empty means all
    assert followup.unknown(state, (2, 9)) == [9]
