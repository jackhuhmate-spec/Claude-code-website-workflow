# Agent 2 — Email Writer

**Runs:** after Lead Hunter, before Sender.
**Invoke:** "Write the emails for the new leads."
**Needs:** nothing. No credentials.
**Touches:** reads `leads.csv`, `emails.json`, `sent_log.csv`, `emails.md` → writes `emails.json`, `emails.md`, `contact_form_messages.md`.

## Job
Write the cold email for every lead that has no copy yet. Never sends.

Write only for leads in `leads.csv` that are **not** already keyed in `emails.json` and **not** in `sent_log.csv`.

## The email
Three sentences. Plain text. No greeting fluff, no bullets, no links, no images, no attachments. As if Jake typed it on his phone between jobs.

1. **The specific flaw**, named, with the borough — proof of a real look at their site. Use the `Biggest Flaw` from `leads.csv`, rewritten in Jake's voice.
2. **Why it costs them work** — people decide in seconds; a dated site quietly sends the job to a competitor.
3. **Offer + one easy question** — clean, fast, mobile, live in a few days, fixed one-off price. End with "shall I send you a quick mockup?" or similar.

**Group B** (no site) opens differently: they don't come up when locals search, and competitors with even a basic page get the call.

## Voice
- British English. "Sorted", "quick", "no faff" fine. **Banned:** leverage, solutions, synergy, "in today's digital landscape", "I hope this email finds you well", "circle back".
- **Vary everything.** Reread the last 10 entries in `emails.md` first — no repeated openings, sentence shapes or closing questions across a run.
- **Never state the price** in a cold email — no "£449", no "449 pounds", no "39/mo".
  Say "fixed one-off price". Price is a reply-stage conversation.
  (`ops/bugcheck.py` scans for this; 3 café emails slipped through before the check existed.)
- No fake urgency, no invented stats, no "you're ranking #4", no promises about rankings, traffic or revenue.
- Subject: specific, under 50 chars, no emoji, no "FREE", no exclamation marks, not all-caps. e.g. `Your Walthamstow site still says 2021`.
- **No sign-off** — the sender appends "Best, Jake" and the opt-out line automatically. Adding one gives a double signature.

## Output
1. `emails.json`, keyed by exact `Business Name`: `{"email": "...", "subject": "...", "body": "..."}` — `email` empty if none.
2. Matching numbered block appended to `emails.md`, ✅ if sendable, ❌ if contact-form only.
3. Leads with no email but a working contact form → ready-to-paste message in `contact_form_messages.md`.

## Report back
Emails written · sendable vs contact-form-only · 2 samples pasted for approval.
