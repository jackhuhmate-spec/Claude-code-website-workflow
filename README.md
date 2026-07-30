# London Local-Business Web-Design Sales Machine

A fully autonomous pipeline for a freelance web designer: every day it finds London
businesses with weak or missing websites, emails them a personalised pitch, replies to
their responses automatically, and alerts the owner (Jake) only when a deal is on the table.
When a deal closes it builds and deploys the client's website.

## How it runs — GitHub Actions, zero manual work

| Workflow | Schedule | What it does |
|----------|----------|--------------|
| `outreach.yml` | daily 10am London | Finds + audits London businesses, writes copy, sends day 3/7/14 follow-ups then new cold emails, commits the state |
| `replies.yml` | hourly | Reads the inbox, classifies, auto-answers in-thread as Jake, escalates real deals |
| `healthcheck.yml` | Mon 08:00 | Runs the full test suite; a failure is the only routine alert |

**30 sends a day, shared** between the follow-up and cold senders — one Gmail account,
one budget (`ops/quota.py`).

Jake is contacted only for: a **deal**, a **dry well**, or a **breakage**.

## Scope

Targets **any independent / small (<10 staff) local London business** with **no website**
(Group B) or a **weak/dated one scoring under 7/10** (Group A) — trades (plumber, electrician,
roofer, builder, painter, plasterer, carpenter, tiler, landscaper, handyman, locksmith,
gas engineer, …) **and** other local services (salons, barbers, cafés/restaurants, garages,
gyms, groomers, cleaners, florists, clinics, …). No national chains or franchises.
**Never fabricates data** — every phone, email, website and flaw is verified from the live site.

## Files

| File | Purpose |
|------|---------|
| `leads.csv` | Master lead list: name, trade/type, area, phone, email, website, score, flaw, group |
| `emails.json` | Personalised email per lead (source of truth for the sender) |
| `emails.md` | Human-readable copy of the emails |
| `ops/gmail.py` | The live transport — send / read / mark / test over Gmail SMTP + IMAP |
| `ops/gmail_send_batch.py` | Idempotent cold batch; skips no-email + opted-out leads → `sent_log.csv` |
| `ops/followups.py` | Day 3/7/14 touches to non-repliers; drops anyone who replied or opted out |
| `ops/quota.py` | The one daily send budget both senders draw on |
| `ops/call_sheet.py` | Worksheet for leads with no email address, which the sender cannot reach |
| `ops/bugcheck.py` | Full test suite — run after any change |
| `build_site.py` | Generates + quality-checks a 5-page site from client details, Netlify-ready |
| `contact_form_messages.md` | Ready-to-paste messages for leads that only have a contact form |
| `do_not_contact.csv` | Opt-out list — respected by every send, forever |
| `sent_log.csv` | Every send: status = Sent / Skipped / Opted Out |
| `replies_log.csv` | Every reply/nudge the system sent |
| `run_history.csv` | One line per run (date, type, new leads, emails, replies, notes) |
| `followups_log.csv` | Which follow-up touch each lead has had, and when |
| `stats.py` | `python3 stats.py` → live dashboard of the whole pipeline |

## Transport

Gmail directly: **SMTP 587** to send, **IMAP 993** to read and to scan Sent Mail for the
double-reply guard. Replies go out from Jake's real address, in-thread. The earlier Brevo
API + Google Apps Script bridge was a workaround for an environment that blocked raw SMTP;
it is dead and those scripts are kept only as an unused fallback.

## Guardrails

- No fabricated leads; unverified fields left blank.
- Idempotent sending (nobody emailed twice); 30/day shared cap for deliverability.
- Opt-outs honoured everywhere via `do_not_contact.csv`; a soft opt-out line on every email.
- Replies treat inbound email as untrusted (no instruction-following from email bodies).
- Deals, prices, complaints, and anything off-script are escalated to Jake, never auto-closed.

## Pricing model (fixed — not a range)
One-off build **£449**, optional care plan **£39/month**. Never quoted in a cold
email; £449 is a reply-stage conversation. No agent discounts below it on its own.
