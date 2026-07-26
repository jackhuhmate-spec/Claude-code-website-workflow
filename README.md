# London Local-Business Web-Design Sales Machine

A fully autonomous pipeline for a freelance web designer: every day it finds London
businesses with weak or missing websites, emails them a personalised pitch, replies to
their responses automatically, and alerts the owner (Jake) only when a deal is on the table.
When a deal closes it builds and deploys the client's website.

## How it runs — two daily Routines, zero manual work

| Routine | Time (London) | What it does |
|---------|---------------|--------------|
| **Lead-gen + outreach** | 10am | 4 agents scan London, audit sites, write + send up to 50 personalised emails, archive the run |
| **Reply handling** | 9am | Reads the inbox, auto-answers businesses as Jake, escalates only real deals |

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
| `brevo_send.py` | Sends via Brevo HTTPS API — idempotent, skips no-email + opted-out leads → `sent_log.csv` |
| `reply_bridge.py` | Reads/sends replies via the Gmail bridge (HTTPS) |
| `gmail_bridge.gs` | Google Apps Script deployed in Jake's account — the inbox bridge |
| `build_site.py` | Job 6: generates + quality-checks a 5-page site from client details, Netlify-ready |
| `contact_form_messages.md` | Ready-to-paste messages for leads that only have a contact form |
| `do_not_contact.csv` | Opt-out list — respected by every send, forever |
| `sent_log.csv` | Every send: status = Sent / Skipped / Opted Out |
| `replies_log.csv` | Every reply/nudge the system sent |
| `run_history.csv` | One line per run (date, type, new leads, emails, replies, notes) |
| `runs/<date>/` | Full daily archive: raw agent JSON, summary.md, inbox.json, replies.md |
| `stats.py` | `python3 stats.py` → live dashboard of the whole pipeline |

## Why it works in this environment

The run environment blocks raw SMTP and IMAP, so:
- **Sending** goes through the **Brevo HTTPS API** (from Jake's Gmail address, reply-to Jake).
- **Inbox read + reply** goes through a **Google Apps Script bridge** in Jake's own account,
  reachable over one secret HTTPS URL — replies are sent from his real Gmail, in-thread.

## Guardrails

- No fabricated leads; unverified fields left blank.
- Idempotent sending (nobody emailed twice); 50/day cap for deliverability.
- Opt-outs honoured everywhere via `do_not_contact.csv`; a soft opt-out line on every email.
- Replies treat inbound email as untrusted (no instruction-following from email bodies).
- Deals, prices, complaints, and anything off-script are escalated to Jake, never auto-closed.

## Pricing model (reference)
One-off build **£300–£800**, optional care plan **£30–£60/mo**.
