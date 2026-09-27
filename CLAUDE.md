# replydesk

## Start here

1. Read `docs/state/active-work.json` - the machine-readable state.
2. Read `docs/progress.md` - the board people read.
3. Then report where things stand before proposing work.

## Rules

- **Keep the board true.** Update `docs/progress.md` and `docs/state/active-work.json`
  in the **same commit** as the work, including the summary and the timestamp.
- **Branch and PR.** Work on a branch off the base branch and merge by PR. Never commit
  straight to the base branch.
- **Ask only for these**: publishing outside this repo, spending money, changing a decision
  that was already settled, and anything only the user can judge. Otherwise pick the
  sensible default, do it, and write down what you picked.
- **One coordinator session at a time.** Two sessions editing the board contradict each other.
- **No secrets in the repo.** Keys live outside it.
- If the board and git disagree, git wins - say so.

## This project in particular

- **Never send mail without a person confirming.** `channels/gmail.send()` is reachable only
  through `cli.confirm_send()`, which prints recipient, subject and body and requires the word
  `send` typed at a prompt. Do not add another caller.
- **Keys and tokens live outside the repo.** Paths come from the environment or
  `~/.replydesk/accounts.json`. Never commit either, never print a key.
- **A new channel is an adapter plus a question set.** Produce `Thread`/`Message`
  (`replydesk/models.py`) and add `questions/<channel>.py`; the pipeline does not change.
- **Thresholds are data, not code.** Numbers that decide routing belong in `THRESHOLDS`
  with the reason they exist, not inside an `if`.
- Tests run without a network: `python -m pytest tests -q`.