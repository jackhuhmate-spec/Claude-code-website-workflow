# Agent 3 — Outreach Sender

**Runs:** daily, after Email Writer.
**Invoke:** "Send today's outreach." Always dry-run first and show Jake before live sending.
**Needs:** `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `SIGN_NAME=Jake`.
**Touches:** reads `emails.json`, `do_not_contact.csv` → writes `sent_log.csv`, `runs/<date>/`, `run_history.csv`.

## Preflight — abort on any failure
1. **`PAUSED` file in repo root → stop immediately.** Report "outreach paused, nothing sent". Jake's kill switch.
2. `python3 ops/gmail.py test` — SMTP + IMAP must both return OK. Any failure → stop, report, send nothing.
3. Confirm `GMAIL_USER` / `GMAIL_APP_PASSWORD` are set. Missing → stop.

## Sequence
1. `python3 ops/gmail_send_batch.py` — **dry run, always first.** Read the output: recipient count, nobody from `do_not_contact.csv` or already in `sent_log.csv`, no truncated or duplicated subjects/bodies.
2. Show Jake the dry-run list. **Wait for his go-ahead on the first run of any new batch.**
3. `python3 ops/gmail_send_batch.py --send --limit 30 --delay 45`
   - **Hard cap 30/day.** This is a personal Gmail, not a bulk sender — going over gets the account flagged.
   - 45s spacing minimum. Never lower it.
4. Follow-ups (day 3/7/14 to non-repliers): only via the idempotent log. Never force a resend.
5. Archive to `runs/<today>/` with a short `summary.md`: leads added, sent, skipped, follow-ups, errors.
6. Append one line to `run_history.csv`.
7. `git add -A && git commit -m "outreach run <date>" && git push`.

## Hard rules
- Never hand-edit `sent_log.csv` or `do_not_contact.csv` to make something re-send. Idempotency is the safety net.
- Never send to an address that isn't in `emails.json`.
- One opt-out = permanent removal. No "one last email".
- If SMTP errors mid-batch: **stop**, keep the partial log, report. Never blind-retry — that double-sends.
- If Gmail returns a rate/spam error, stop for the day and tell Jake. Don't retry tomorrow at a higher volume.

## Report back
Sent / skipped / opted-out counts · follow-ups · errors · commit hash.
