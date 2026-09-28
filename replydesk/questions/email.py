"""What we ask the judge about an email thread.

Written in English because that is Jev's strongest language; the email itself stays in whatever
language it arrived in. Every question is one snap judgement a competent person makes in a second
— anything that needs reasoning is split into two questions and combined in code.

Labels are what a person reads in the UI; keys are what code branches on.
"""
from __future__ import annotations

QUESTIONS: dict = {
    "needs_reply": {
        "type": "noul",
        "instructions": "Does the latest message in `thread` expect a reply from us?",
        "criteria": {
            "true": "It asks a question, requests something, or leaves a decision to us.",
            "false": "It is an automated notification, a newsletter, a receipt, a read-only FYI, "
                     "or a closing 'thanks, nothing else needed'.",
        },
    },
    "intent": {
        "type": "choice",
        "instructions": "What does the sender of the latest message in `thread` mainly want?",
        "criteria": {
            "ask_question": "They want information or an explanation.",
            "request_action": "They want us to do something concrete: send a file, fix, ship, refund.",
            "schedule": "They want to agree on a time, a meeting, or a deadline.",
            "complaint": "They are unhappy about something that already happened and want it addressed.",
            "sales_inquiry": "They are asking about buying, pricing, or a quote.",
            "billing": "Invoices, payment, receipts, or subscription charges.",
            "introduction": "Cold outreach, a pitch, or a first contact with no concrete ask.",
            "closing": "They are wrapping up: thanks, confirmation, no further action wanted.",
            "other": "None of the above.",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How soon does the latest message in `thread` need an answer, judged by what "
                        "it says, not by how politely it is written?",
        "criteria": [
            "No deadline at all; answering next week changes nothing.",
            "Expected within a few days; normal business pace.",
            "Needed today; someone is waiting to act on it.",
            "Blocking right now; money, a deployment, or a legal deadline is at stake.",
        ],
    },
    "frustration": {
        "type": "score",
        "instructions": "How frustrated does the sender of the latest message sound?",
        "criteria": [
            "Neutral or warm.",
            "Businesslike but pointed; chasing an answer.",
            "Clearly annoyed; mentions repeated attempts or broken promises.",
            "Angry; threatens to escalate, cancel, or go public.",
        ],
    },
    "answerable_here": {
        "type": "noul",
        "instructions": "Can the latest message be answered using only `thread` and `context`, "
                        "without looking up a fact nobody in this thread has stated?",
        "criteria": {
            "true": "Everything needed is already in the thread or the context.",
            "false": "Answering needs a number, a date, a policy, or a record that is not here.",
        },
    },
    "needs_human": {
        "type": "noul",
        "instructions": "Should a person write this reply themselves rather than edit a draft?",
        "criteria": {
            "true": "Legal exposure, a refund or credit decision, a complaint about a named person, "
                    "bad news about someone's job, or anything where a wrong sentence is expensive.",
            "false": "Ordinary correspondence where a draft is a reasonable starting point.",
        },
    },
    "commitment_made": {
        "type": "noul",
        "instructions": "Did we promise something earlier in `thread` that has not been delivered yet?",
        "criteria": {
            "true": "We said we would send, fix, check or decide something, and no later message "
                    "shows it happened.",
            "false": "No open promise from us, or the promise was already kept.",
        },
    },
}

LABELS = {
    "needs_reply": "답장이 필요한가",
    "intent": "상대가 원하는 것",
    "urgency": "긴급도",
    "frustration": "불만도",
    "answerable_here": "여기 있는 정보로 답할 수 있나",
    "needs_human": "사람이 직접 써야 하나",
    "commitment_made": "우리가 한 약속이 남아 있나",
}

INTENT_LABELS = {
    "ask_question": "질문", "request_action": "처리 요청", "schedule": "일정 조율",
    "complaint": "불만 제기", "sales_inquiry": "구매 문의", "billing": "결제·청구",
    "introduction": "첫 연락·제안", "closing": "마무리", "other": "기타",
}

# Where a probability turns into a decision. Kept together and named, because these are the numbers
# a team argues about — and because "0.59 vs 0.6" flipping a refund thread between "draft it" and
# "a person writes this" is exactly the case that should be visible, not buried in an if.
THRESHOLDS = {
    "needs_reply": 0.5,      # below this the drafting model is never called
    "needs_human": 0.5,      # at or above, route to a person instead of showing a draft
    "answerable_here": 0.4,  # below this, drafts must promise a check rather than an answer
    "commitment_open": 0.6,  # at or above, the draft has to say where the promise stands
    "urgent_now": 2.5,       # on the 0..3 urgency scale: answer with a time, not "soon"
    "urgent_today": 1.5,
    "frustrated": 1.5,
    "unsupported_claim": 0.5,  # at or above, the draft is dropped: it asserts something untrue
}


def route(answers: dict) -> str:
    """What should happen to this thread: "skip", "human", or "draft"."""
    if answers.get("needs_reply", {}).get("value", 1.0) < THRESHOLDS["needs_reply"]:
        return "skip"
    if answers.get("needs_human", {}).get("value", 0.0) >= THRESHOLDS["needs_human"]:
        return "human"
    return "draft"


# A generative model will happily write "I have already applied" into a reply to an application
# form it has just read. The prompt forbids it and the model does it anyway, so the draft gets
# judged too: one yes/no per candidate, and anything that claims something the thread does not
# support is dropped before a person ever sees it.
UNSUPPORTED_CLAIM = (
    "Does `draft` state as already done something that `thread` and `context` do not show "
    "happened — for example claiming we applied, paid, sent, fixed or confirmed something? "
    "An intention ('I would like to', 'I will send it by tonight') or a question is not a claim."
)

RANK_INSTRUCTIONS = (
    "Which of these drafts should be sent as the reply to the latest message in `thread`? "
    "Prefer the one that answers what was actually asked, keeps any promise we already made, "
    "and matches the sender's urgency and tone. Length is not a virtue."
)


def guidance(answers: dict) -> str:
    """The judgement, compressed into the note the drafting model gets.

    Only the parts that change what to write. The model decides how to say it.
    """
    lines = []
    intent = answers.get("intent", {}).get("value")
    if intent:
        lines.append(f"- The sender mainly wants: {intent}")
    urgency = answers.get("urgency", {}).get("value")
    if isinstance(urgency, float):
        if urgency >= THRESHOLDS["urgent_now"]:
            lines.append("- This is blocking someone right now: lead with the answer or a time, no preamble.")
        elif urgency >= THRESHOLDS["urgent_today"]:
            lines.append("- They need it today: give a concrete time, not 'soon'.")
    frustration = answers.get("frustration", {}).get("value")
    if isinstance(frustration, float) and frustration >= THRESHOLDS["frustrated"]:
        lines.append("- They are frustrated: acknowledge the delay in one short sentence, then the substance. "
                     "Do not over-apologise and do not explain internal reasons.")
    if answers.get("commitment_made", {}).get("value", 0) >= THRESHOLDS["commitment_open"]:
        lines.append("- We owe them something we promised earlier: say where it stands and when it lands.")
    if answers.get("answerable_here", {}).get("value", 1) < THRESHOLDS["answerable_here"]:
        lines.append("- The thread does not contain what is needed to answer: say what we will check "
                     "and by when, instead of inventing a fact.")
    if answers.get("needs_human", {}).get("value", 0) >= THRESHOLDS["needs_human"]:
        lines.append("- Sensitive: keep it short and factual, promise no outcome, commit only to a next step.")
    return "Judgement (follow it for what to say; wording is yours):\n" + "\n".join(lines) if lines else ""
