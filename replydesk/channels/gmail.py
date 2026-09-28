"""Gmail as a channel: read threads that are waiting on us, stage a draft the person can send.

Sending is supported and gated. `stage()` writes a draft; `send()` actually mails, and the only
caller is a CLI path that prints the message and asks first (see cli.confirm_send). Nothing in the
judge-write-rank pipeline can reach `send()` on its own — a model never triggers it.

It also never spends a judgement on mail Gmail already sorted: spam and promotions are excluded in
the server-side query, so the cheapest filter runs before any model sees a word (see SKIP_LABELS).

OAuth: a desktop client's credentials.json, and a token file the first consent writes next to it.
Both live outside the repository; their paths come from the environment.
"""
from __future__ import annotations

import base64
import datetime as dt
import os
import random
import re
import time
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ..models import Message, Thread

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",   # read threads
    "https://www.googleapis.com/auth/gmail.compose",    # create drafts
    "https://www.googleapis.com/auth/gmail.send",       # send, only from an explicit confirmation
]

# Gmail has already classified these; paying a model to re-decide is waste. Anything that slips
# through still meets the judge's own needs_reply question.
SKIP_LABELS = ("SPAM", "TRASH", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_FORUMS")
DEFAULT_QUERY = "in:inbox -in:chats newer_than:14d"

# A full thread read costs ~10 quota units and the per-user budget is per minute, so a tight loop
# over a busy mailbox trips "Quota exceeded ... Units per minute per user" on the tenth-odd thread.
RETRYABLE = frozenset({403, 429, 500, 502, 503})
MAX_TRIES = 5

_QUOTE = re.compile(r"^\s*(>|On .*wrote:|\d{4}년 .*작성:|-{2,}\s*Original Message)", re.M)


def _paths() -> tuple[Path, Path]:
    creds = Path(os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json"))
    token = Path(os.environ.get("GMAIL_TOKEN_FILE", str(creds.with_name("gmail_token.json"))))
    return creds, token


def _service(account_hint: str = ""):
    """Load the token, refresh it, or run the one-time consent in a browser.

    The consent is the person's to give: this opens their browser and waits, it never types.
    """
    creds_file, token_file = _paths()
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES) if token_file.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
        creds = flow.run_local_server(port=0, login_hint=account_hint or None,
                                      prompt="consent" if not account_hint else "select_account")
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _call(request, tries: int = MAX_TRIES):
    """Run a Gmail request, backing off when the mailbox says we are asking too fast.

    403 is overloaded on this API: a rate limit and a permission failure share the code, so only
    the quota wording is retried — a real permission error should surface immediately.
    """
    from googleapiclient.errors import HttpError

    for attempt in range(tries):
        try:
            return request.execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", 0)
            quota = status != 403 or b"uota" in (exc.content or b"")
            if status not in RETRYABLE or not quota or attempt == tries - 1:
                raise
            time.sleep(min(2 ** attempt, 20) + random.random())
    raise RuntimeError("unreachable")


def _decode(part) -> str:
    data = (part.get("body") or {}).get("data")
    return base64.urlsafe_b64decode(data).decode("utf-8", "replace") if data else ""


def _body(payload) -> str:
    """Prefer text/plain; fall back to stripping tags out of the HTML part."""
    stack, html = [payload], ""
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            text = _decode(part)
            if text.strip():
                return text
        if mime == "text/html" and not html:
            html = _decode(part)
        stack.extend(part.get("parts") or [])
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+\n", "\n", re.sub(r"<[^>]+>", " ", text))


def clean(text: str, limit: int = 2500) -> str:
    """Drop the quoted history and signature noise: the thread already carries the earlier turns.

    Links survive the trim. A recruitment mail puts "apply here: forms.gle/..." near the bottom,
    and cutting it off is how the judge comes to think a reply is the way to answer.
    """
    cut = _QUOTE.search(text)
    if cut:
        text = text[:cut.start()]
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= limit:
        return text
    dropped = [u for u in re.findall(r"https?://\S+", text[limit:])][:5]
    kept = text[:limit].rstrip()
    return kept + ("\n[링크] " + " ".join(dropped) if dropped else "")


def _header(headers: list, name: str) -> str:
    return next((h["value"] for h in headers if h["name"].lower() == name.lower()), "")


def _when(raw: str) -> dt.datetime | None:
    try:
        return parsedate_to_datetime(raw).astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


class GmailChannel:
    """One mailbox. `account` is only a hint for the consent screen — the token decides."""

    name = "gmail"

    def __init__(self, account: str = "", query: str = DEFAULT_QUERY):
        self.account = account
        self.query = query
        self._service = None
        self._me = ""

    @property
    def service(self):
        if self._service is None:
            self._service = _service(self.account)
            self._me = _call(self._service.users().getProfile(userId="me"))["emailAddress"]
        return self._service

    def _to_thread(self, raw: dict) -> Thread | None:
        messages = []
        subject = ""
        for m in raw.get("messages", []):
            labels = set(m.get("labelIds") or [])
            if labels & set(SKIP_LABELS):
                return None                      # Gmail already judged this thread
            if "DRAFT" in labels:
                # Our own unsent draft sits in the thread. It is not a reply until it is sent, and
                # counting it as one makes a staged thread vanish from the next triage run.
                continue
            headers = m["payload"]["headers"]
            sender = _header(headers, "From")
            subject = subject or _header(headers, "Subject")
            text = clean(_body(m["payload"]))
            if not text:
                continue
            mine = self._me and self._me.lower() in sender.lower()
            messages.append(Message(
                side="us" if mine else "them",
                text=text,
                sender="" if mine else re.sub(r"\s*<.*?>", "", sender).strip('" '),
                at=_when(_header(headers, "Date")),
            ))
        if not messages:
            return None
        last = raw["messages"][-1]["payload"]["headers"]
        return Thread(id=raw["id"], channel="email", subject=subject, messages=tuple(messages),
                      context={"mailbox": self._me,
                               # kept for threading a reply: Gmail groups by these, not by subject
                               "reply_to": _header(last, "Reply-To") or _header(last, "From"),
                               "message_id": _header(last, "Message-ID")})

    def fetch(self, limit: int = 20, scan: int | None = None) -> list[Thread]:
        """Newest threads that are waiting on us.

        `scan` caps how many threads are opened, which is what the quota actually counts: a mailbox
        full of newsletters would otherwise read a hundred threads to find five worth answering.
        """
        scan = scan or limit * 2
        listed = _call(self.service.users().threads().list(
            userId="me", q=self.query, maxResults=scan))
        threads = []
        for ref in listed.get("threads", [])[:scan]:
            raw = _call(self.service.users().threads().get(userId="me", id=ref["id"], format="full"))
            thread = self._to_thread(raw)
            if thread and thread.needs_reply:
                threads.append(thread)
            if len(threads) >= limit:
                break
        return threads

    def _raw(self, thread: Thread, text: str) -> str:
        """RFC 5322 message, threaded onto the mail we are answering.

        Built with EmailMessage rather than joined by hand: a Korean subject has to go out as
        RFC 2047 encoded words, and hand-joined headers produced mojibake in the mailbox.
        """
        mail = EmailMessage()
        mail["To"] = thread.context.get("reply_to", "")
        mail["Subject"] = (thread.subject if thread.subject.lower().startswith("re:")
                           else f"Re: {thread.subject}")
        message_id = thread.context.get("message_id", "")
        if message_id:
            mail["In-Reply-To"] = message_id
            mail["References"] = message_id
        mail.set_content(text, subtype="plain", charset="utf-8")
        return base64.urlsafe_b64encode(mail.as_bytes()).decode()

    def stage(self, thread: Thread, text: str) -> str:
        """Create a Gmail draft in the thread. The person opens it, edits, and sends."""
        draft = _call(self.service.users().drafts().create(
            userId="me", body={"message": {"raw": self._raw(thread, text), "threadId": thread.id}}))
        return f"Gmail 임시보관함 (draft {draft['id']})"

    def send(self, thread: Thread, text: str) -> str:
        """Send the reply. Irreversible and outward-facing: callers must have asked a person first.

        Kept separate from `stage` so "put it somewhere safe" and "mail it to someone" can never be
        the same call by accident.
        """
        to = thread.context.get("reply_to")
        if not to:
            raise ValueError("받는 사람을 알 수 없어 보내지 않았습니다")
        sent = _call(self.service.users().messages().send(
            userId="me", body={"raw": self._raw(thread, text), "threadId": thread.id}))
        return f"{to} 에게 발송됨 (message {sent['id']})"
