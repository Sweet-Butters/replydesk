# replydesk

한국어: [README.ko.md](README.ko.md)

A reply copilot that **judges before it writes**, for inboxes a person is responsible for — email
today, chat and support queues next.

Most assistants hand a language model the thread and ask for a reply. This one asks a decision
model seven typed questions first — is a reply expected, what do they want, how urgent, how annoyed,
can it be answered from what we have, should a human write this, did we promise something — and only
then writes three drafts against those answers. A person picks one, edits it, and sends it.

```
                    ┌──────────── judge (Jev) ────────────┐
 thread ──────────► │ needs_reply  0.95                   │
 (any channel)      │ intent       request_action (0.37)  │──► guidance ──┐
                    │ urgency      2.3 / 3                │               │
                    │ frustration  2.3 / 3                │               ▼
                    │ answerable   0.31                   │       write (Gemini)
                    │ needs_human  0.26                   │        3 drafts
                    │ commitment   0.06                   │               │
                    └─────────────────────────────────────┘               ▼
                                                              rank (Jev) ──► person sends
```

## Why a decision model for the first half

`intent == "billing"` with confidence 0.93 is something code can branch on; a paragraph of prose is
not. Low confidence is a routing signal, not a failure. And because the judgement is cheap
(~1,900 input tokens, about $0.00008 a thread) it can run over a whole inbox, while drafting — the
expensive half — runs only on the threads a person is actually about to answer.

Measured on the sample inbox: judgement only, 0.4 s a thread; judgement + three drafts + ranking,
2.2 s.

## Quick start

```bash
pip install -e .
export TYPESAFE_API_KEY=...        # or TYPESAFE_API_KEY_FILE=/path/to/key
export GEMINI_API_KEY=...          # or GEMINI_API_KEY_FILE=/path/to/key

python -m replydesk triage         # judge every waiting thread, one line each
python -m replydesk reply t1       # judge one thread, write three drafts, rank them
python -m replydesk reply t1 --json
```

Out of the box it runs against a fixed sample inbox, so you can see the whole pipeline before
connecting a mailbox. Keys are read from the environment or from a file the environment points at;
they are never written to the repository and never logged.

## Triage output

```
[t1] 긴급 2.3/3 · 처리 요청 · 초안 가능  · 결제가 안 됩니다 (주문 A-2291)
[t2] 긴급 2.0/3 · 처리 요청 · 초안 가능  · Re: 견적서 회신 부탁드립니다
[t3] 긴급 0.0/3 · 기타      · 초안 가능  · [뉴스레터] 9월 제품 업데이트
[t4] 긴급 2.1/3 · 처리 요청 · 사람이 직접 · 환불 요청합니다
```

The refund demand routes itself to a person; the newsletter scores 0.0 urgency and never reaches
the drafting model.

## Adding a channel

A channel turns whatever it has into `Thread` and `Message` (`replydesk/models.py`) and, if it can,
stages a chosen draft where the person will send it. Everything above that line is channel-agnostic.

| Channel | Input | Status |
|---|---|---|
| Sample inbox | fixed threads | shipped |
| Email | Gmail API | shipped — read, draft, send |
| Support queue | helpdesk API | planned |
| Community & social comments | platform API | planned — check each platform's terms first |
| KakaoTalk | screen capture + OCR (no API) | planned; see [notes](docs/kakaotalk.md) |

Question sets live beside channels (`replydesk/questions/`). Email asks about urgency and open
promises; a support queue would ask about refund authority and SLA; a comment feed would ask whether
a reply is worth making at all. The pipeline does not change.

## Connecting Gmail

```bash
pip install -e ".[gmail]"
export GMAIL_CREDENTIALS_FILE=/path/to/credentials.json   # a desktop OAuth client
export GMAIL_TOKEN_FILE=/path/to/token.json               # one per mailbox
python -m replydesk.connect --account you@example.com     # one-time consent, in your browser

python -m replydesk triage --channel gmail
python -m replydesk reply <thread id> --channel gmail --stage   # into the mailbox as a draft
python -m replydesk reply <thread id> --channel gmail --send    # shows it, then asks
```

### Several mailboxes

Name them once in `~/.replydesk/accounts.json` (or wherever `REPLYDESK_ACCOUNTS` points) and the
paths stop travelling on the command line. The file holds paths and queries — never a key or token:

```json
{
  "work":     {"channel": "gmail", "email": "me@company.com",
               "credentials": "/keys/client.json", "token": "/keys/work.json"},
  "personal": {"channel": "gmail", "email": "me@gmail.com",
               "credentials": "/keys/client_personal.json", "token": "/keys/personal.json",
               "query": "in:inbox newer_than:7d"}
}
```

```bash
python -m replydesk triage --channel gmail --account work
```

Scopes: `gmail.readonly`, `gmail.compose`, `gmail.send`. Spam, promotions, social and forum mail are
excluded from the query, so Gmail's own classification does the first filtering pass for free.

## A digest on your phone

`digest` judges every waiting thread and prints one phone-sized summary — counts by route, then
the threads that need the person, most urgent first:

```
[replydesk] 9/29 메일 40건
답장 4 · 폼·링크 3
🔴 [참석 안내] 9/30(수) 스타트업 성장 세미나
· Re: 견적서 회신 부탁드립니다
```

It can push that to KakaoTalk's note-to-self room:

```bash
python -m replydesk.notify.kakao                 # one-time consent
python -m replydesk digest --channel gmail --account work,personal --notify kakao
```

This uses Kakao's 메모 API, and that is the whole point of choosing it: **Kakao has no API that
reads a personal chat, and messaging anyone else requires a reviewed business app.** The notifier
can write exactly one message, to the account holder, in their own room. It is not a channel —
nothing in the judge-write-rank pipeline can reach it, and it can never address another person.

Setup is walked through in **[docs/kakao-setup.md](docs/kakao-setup.md)**, including the two places the console actually trips people up. In short: a Kakao Developers app with 카카오 로그인 on, the `talk_message` consent item enabled, and
`http://localhost:8123/oauth` as a redirect URI; the REST API key goes in `KAKAO_REST_API_KEY`
(or `KAKAO_REST_API_KEY_FILE`). The subjects in the digest leave your machine for Kakao's servers —
if that is not acceptable, run `digest` without `--notify`.

## Answering the digest

KakaoTalk is one-way — nothing can read what you type in your own note-to-self room — so the
instruction channel is mail. `--mail` also sends the digest to your own address with every
actionable thread numbered, and replying to it is how you give an order:

```
2번 초안          → draft a reply to thread 2, into your drafts folder
2, 5번 초안       → several at once
3번 건너뛰기      → mark it handled; it leaves tomorrow's list
전체 건너뛰기     → clear the list
```

```bash
python -m replydesk digest --channel gmail --account work,personal --notify kakao --mail
python -m replydesk commands --channel gmail     # reads the replies and acts on them
```

Two properties make a mailbox safe to take orders from:

- **Only a reply to a digest we sent counts.** `commands` never searches the mailbox for
  instructions; it opens the one thread this program created and reads what arrived after its own
  message. A stranger cannot mail you a command, because their mail is not in that thread.
- **The verbs are a closed set and none of them sends.** The strongest thing a reply can cause is
  a draft appearing in your own drafts folder. Sending still requires `--send` and a typed
  confirmation at a terminal.

Unrecognised lines are ignored rather than guessed at, and the run reports what it understood.

## What it will not do

- **It does not send on its own.** `send()` is unreachable from the pipeline: a person passes
  `--send`, sees the recipient, subject and body, and types `send` at a prompt. A thread the judge
  routed to a human is refused outright unless `--force` is added.
- **It does not invent facts.** The drafting rules forbid dates, prices and policies that are not in
  the thread; when an answer needs a lookup, the draft says what will be checked and by when.
- **It does not obey the mail.** Text inside a thread that looks like an instruction is treated as
  correspondence, not as a command.

## Credits

The judge-then-write-then-rank shape is the one used by
[jev-chat-windows](https://github.com/jev-chat/jev-chat-windows) (MIT), which I contributed Korean
support to. No code is copied from it: this repository is written for API-based channels and carries
no GUI dependency.

Decisions come from [TypeSafe's Jev](https://docs.typesafe.ai/); drafts from Gemini.

MIT licensed.
