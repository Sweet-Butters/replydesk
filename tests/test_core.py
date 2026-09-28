"""Tests for everything that does not need a network: shapes, parsing, and the judgement rules.

The model calls are covered by `python -m replydesk reply t1` against the sample inbox; what is
worth locking down here is the logic that would silently corrupt a judgement.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os

import pytest

from replydesk import jev
from replydesk.channels.sample import SampleChannel
from replydesk.draft import _parse
from replydesk.models import Draft, Message, Result, Thread
from replydesk.questions import email as email_q


def thread(*sides: str) -> Thread:
    msgs = tuple(Message(s, f"{s} 메시지", sender=s, at=dt.datetime(2026, 9, 28, 9, i))
                 for i, s in enumerate(sides))
    return Thread(id="x", channel="email", subject="제목", messages=msgs)


def test_needs_reply_follows_who_spoke_last():
    assert thread("us", "them").needs_reply
    assert not thread("them", "us").needs_reply
    assert not Thread(id="empty", channel="email").needs_reply


def test_state_keeps_only_the_recent_window_and_drops_empty_fields():
    state = thread(*(["them"] * 20)).as_state(keep=5)
    assert len(state["thread"]) == 5
    assert "context" not in state          # empty context is not worth a token
    assert state["thread"][0]["from"] == "them"


def test_latest_from_them_ignores_our_own_replies():
    t = Thread(id="t", channel="email", messages=(
        Message("them", "먼저"), Message("us", "우리"), Message("them", "나중")))
    assert t.latest_from_them.text == "나중"


def test_normalize_reports_noul_certainty_as_distance_from_a_coin_flip():
    assert jev.normalize({"type": "noul", "noul": 0.5})["confidence"] == 0.0
    assert jev.normalize({"type": "noul", "noul": 1.0})["confidence"] == 1.0
    assert jev.normalize({"type": "noul", "noul": 0.0})["confidence"] == 1.0
    assert jev.normalize({"type": "noul", "noul": 0.75})["confidence"] == pytest.approx(0.5)


def test_normalize_carries_the_distribution_for_choice_and_score():
    choice = jev.normalize({"type": "choice", "choice": "billing", "confidence": 0.8,
                            "probabilities": {"billing": 0.8, "other": 0.2}})
    assert choice["value"] == "billing" and choice["probabilities"]["other"] == 0.2
    score = jev.normalize({"type": "score", "score": 2.4, "confidence": 0.7,
                           "legend": {"0": "낮음"}, "probabilities": {"2": 0.6}})
    assert score["value"] == 2.4 and score["legend"]["0"] == "낮음"


def test_normalize_refuses_an_unknown_answer_type():
    with pytest.raises(ValueError):
        jev.normalize({"type": "essay", "text": "..."})


@pytest.mark.parametrize("raw", [
    '["첫째", "둘째", "셋째"]',
    '```json\n["첫째", "둘째", "셋째"]\n```',
    '1. 첫째\n2. 둘째\n3. 셋째',
])
def test_parse_recovers_three_drafts_from_the_shapes_models_actually_emit(raw):
    assert _parse(raw) == ["첫째", "둘째", "셋째"]


def test_parse_keeps_at_most_three_and_drops_blanks():
    assert _parse('["하나", "", "둘", "셋", "넷"]') == ["하나", "둘", "셋"]


def test_guidance_speaks_up_only_about_what_changes_the_reply():
    calm = {"intent": {"value": "ask_question"}, "urgency": {"type": "score", "value": 0.2},
            "frustration": {"type": "score", "value": 0.1}}
    assert "blocking" not in email_q.guidance(calm)

    urgent = dict(calm, urgency={"type": "score", "value": 2.8},
                  frustration={"type": "score", "value": 2.0},
                  commitment_made={"type": "noul", "value": 0.9},
                  answerable_here={"type": "noul", "value": 0.2})
    note = email_q.guidance(urgent)
    assert "blocking" in note and "frustrated" in note
    assert "promised" in note and "does not contain" in note


def test_guidance_is_empty_when_the_judge_said_nothing_actionable():
    assert email_q.guidance({}) == ""


def test_route_sends_the_sensitive_and_the_pointless_somewhere_other_than_the_writer():
    ordinary = {"needs_reply": {"value": 0.9}, "needs_human": {"value": 0.1}}
    assert email_q.route(ordinary) == "draft"
    assert email_q.route(dict(ordinary, needs_reply={"value": 0.2})) == "skip"
    assert email_q.route(dict(ordinary, needs_human={"value": 0.55})) == "human"


def test_route_is_decided_by_the_named_thresholds_not_by_scattered_numbers():
    edge = email_q.THRESHOLDS["needs_human"]
    base = {"needs_reply": {"value": 0.9}}
    assert email_q.route(dict(base, needs_human={"value": edge})) == "human"
    assert email_q.route(dict(base, needs_human={"value": edge - 0.01})) == "draft"


def test_result_best_is_the_top_ranked_draft():
    result = Result(thread=thread("them"), answers={},
                    drafts=(Draft("낮음", 0.2), Draft("높음", 0.7)))
    assert result.best.text == "높음"
    assert Result(thread=thread("them"), answers={}).best is None


def test_every_question_declares_a_type_the_judge_understands():
    for qid, q in email_q.QUESTIONS.items():
        assert q["type"] in {"noul", "choice", "score"}, qid
        assert q["instructions"].strip(), qid
        assert qid in email_q.LABELS, f"{qid} has no Korean label"
        if q["type"] == "choice":
            assert set(q["criteria"]) <= set(email_q.INTENT_LABELS), qid
        if q["type"] == "score":
            assert len(q["criteria"]) >= 2, qid


def test_sample_inbox_covers_the_cases_the_questions_exist_to_separate():
    threads = SampleChannel().fetch()
    assert {t.id for t in threads} == {"t1", "t2", "t3", "t4"}
    assert all(t.needs_reply for t in threads)
    assert any(t.context.get("refund_policy") for t in threads)   # the human-only case


def test_send_is_refused_for_anything_the_judge_routed_to_a_person():
    from replydesk.cli import confirm_send

    class Channel:
        sent = False

        def send(self, thread, text):
            Channel.sent = True
            return "sent"

    result = Result(thread=thread("them"),
                    answers={"needs_reply": {"value": 0.9}, "needs_human": {"value": 0.9}},
                    drafts=(Draft("본문", 0.9),))
    assert confirm_send(Channel(), result.thread, result) == 3   # routed to a human
    assert not Channel.sent


def test_send_goes_through_only_once_a_person_has_answered():
    from replydesk.cli import confirm_send

    class Channel:
        def __init__(self):
            self.sent = []

        def send(self, thread, text):
            self.sent.append(text)
            return "sent"

    ok = Result(thread=thread("them"),
                answers={"needs_reply": {"value": 0.9}, "needs_human": {"value": 0.1}},
                drafts=(Draft("보낼 본문", 0.9),))
    channel = Channel()
    assert confirm_send(channel, ok.thread, ok, yes=True) == 0
    assert channel.sent == ["보낼 본문"]


def test_named_account_exports_paths_without_ever_holding_a_secret(tmp_path, monkeypatch):
    from replydesk import accounts

    book = tmp_path / "accounts.json"
    book.write_text(json.dumps({"work": {"channel": "gmail", "email": "me@x.com",
                                         "credentials": str(tmp_path / "c.json"),
                                         "token": str(tmp_path / "t.json"),
                                         "query": "in:inbox newer_than:3d"}}), encoding="utf-8")
    monkeypatch.setenv("REPLYDESK_ACCOUNTS", str(book))
    monkeypatch.delenv("GMAIL_CREDENTIALS_FILE", raising=False)

    assert accounts.names() == ["work"]
    entry = accounts.resolve("work")
    assert entry["email"] == "me@x.com" and entry["query"].startswith("in:inbox")
    assert os.environ["GMAIL_CREDENTIALS_FILE"].endswith("c.json")
    assert os.environ["GMAIL_TOKEN_FILE"].endswith("t.json")
    with pytest.raises(KeyError):
        accounts.resolve("nope")


def test_no_account_book_is_not_an_error(tmp_path, monkeypatch):
    from replydesk import accounts

    monkeypatch.setenv("REPLYDESK_ACCOUNTS", str(tmp_path / "missing.json"))
    assert accounts.load() == {} and accounts.names() == []


def test_a_staged_draft_does_not_count_as_having_replied():
    """A draft sits in the Gmail thread with a DRAFT label; it is not a sent reply."""
    from replydesk.channels.gmail import GmailChannel

    channel = GmailChannel()
    channel._me = "me@x.com"
    raw = {"id": "t", "messages": [
        {"labelIds": ["INBOX"], "payload": {"mimeType": "text/plain",
         "headers": [{"name": "From", "value": "Them <them@x.com>"},
                     {"name": "Subject", "value": "질문"},
                     {"name": "Message-ID", "value": "<1@x>"}],
         "body": {"data": base64.urlsafe_b64encode("물어봅니다".encode()).decode()}}},
        {"labelIds": ["DRAFT"], "payload": {"mimeType": "text/plain",
         "headers": [{"name": "From", "value": "me@x.com"}],
         "body": {"data": base64.urlsafe_b64encode("아직 안 보낸 초안".encode()).decode()}}},
    ]}
    thread = channel._to_thread(raw)
    assert [m.side for m in thread.messages] == ["them"]
    assert thread.needs_reply


def test_a_form_link_survives_the_body_trim():
    """The apply-here link sits at the bottom of a recruitment mail; trimming it away is what made
    the judge think a reply was the way to answer."""
    from replydesk.channels.gmail import clean

    body = ("안내문 " * 900) + "\n참가신청(구글폼) https://forms.gle/ABC123\n문의: staff@x.ac.kr"
    trimmed = clean(body, limit=500)
    assert len(trimmed) < len(body)
    assert "https://forms.gle/ABC123" in trimmed


def test_route_stops_before_the_writer_when_the_action_lives_in_a_form():
    base = {"needs_reply": {"value": 0.9}, "needs_human": {"value": 0.1}}
    assert email_q.route(base) == "draft"
    assert email_q.route(dict(base, action_elsewhere={"value": 0.98})) == "elsewhere"
    assert email_q.route(dict(base, action_elsewhere={"value": 0.2})) == "draft"
