# London Tradesman Web-Design Sales Machine

A semi-automated pipeline for a freelance web designer: find London tradesmen with weak
or missing websites, contact them with genuinely personalised emails, manage the replies,
and build the site when a deal closes.

## What's in here

| File | Job | What it does |
|------|-----|--------------|
| `leads.csv` | 1–3 | Verified leads: name, trade, area, phone, email, website, score (1–10), biggest flaw, group |
| `emails.md` | 4 | Human-readable review copy of all personalised emails |
| `emails.json` | 4 | Machine-readable source the sender reads from |
| `send_emails.py` | 4 | Gmail SMTP sender → writes `sent_log.csv` (dry-run by default) |
| `reply_monitor.py` | 5 | Daily IMAP check → categorises replies, **drafts** responses (never auto-sends) |
| `build_site.py` | 6 | Generates a modern 5-page mobile-first site from client details, ready for Netlify |
| `example_client.json` | 6 | Sample input for `build_site.py` |

## The leads (honest state)

**13 verified leads** (12 Group A + 1 Group B), every one hand-audited by actually loading
the homepage. Only sites scoring **under 7/10** are kept — anything modern was dropped, per
the brief. Areas covered: Walthamstow ×2, Enfield, Ilford, Shepherds Bush, Brixton,
Tottenham, Barnet, Woolwich, Hackney, Croydon, Lewisham, Peckham (12 of your 15 target
areas; Wandsworth, Ealing and Stratford returned only modern sites or duplicates).
**9 publish a usable email; 4 only have a contact form** and are skipped by the sender.
The Group B lead (East Peckham Plumbers) is a genuine no-website business — Facebook page
only — with a real published phone and email.

### Two things you should know about the data

1. **I did not invent any lead data.** Phone numbers, emails, websites and flaws are all
   real and verified from the live sites. Where a business publishes no email, the field is
   blank — never guessed. Sending "your website is embarrassing" to a *guessed* address, or
   to the wrong real person, is exactly the kind of mistake that gets **your** domain
   reported, so the file only contains what's confirmed.

2. **Group B (no website) and hitting a round "20" aren't things I can verify remotely.**
   A business with no site produces nothing to fetch, and directories (Checkatrade,
   MyBuilder, Yell) deliberately hide phone/email behind a button. Auditing ~13 live sites
   yielded these 8 genuinely-weak ones — most independents who *have* a site now have a
   decent one. To scale the list, the reliable source is **you** walking Google Maps for a
   given postcode (the "no website" ones are visible there), or a paid data provider with
   opt-in contacts. I can process any list you gather through the exact same pipeline.

## Sending emails (Job 4) — how to do it safely

The sender **defaults to a dry-run** — it prints what would go out and writes the log, but
sends nothing until you pass `--send`.

```bash
# 1. Preview (safe, already run for you — see sent_log.csv):
python3 send_emails.py

# 2. When you've reviewed emails.md and want to send for real:
GMAIL_USER=you@gmail.com \
GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" \
python3 send_emails.py --send --sign "Your Name" --delay 60
```

Use a **Gmail App Password** (Google Account → Security → 2-Step Verification → App
passwords), not your normal password.

### One compliance note worth 30 seconds
Under UK PECR/GDPR, unsolicited marketing email to **sole traders** (which is most of these)
needs a lawful basis, unlike email to registered limited companies. In practice, keep it
low-volume, genuinely relevant, one message with a clear opt-out, and **honour any "remove"
reply instantly** — that's what keeps you off blocklists and out of trouble. The reply
monitor already flags "Not Interested" so you never contact those again. This protects your
sending reputation as much as it protects you legally.

## Managing replies (Job 5)

```bash
GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" \
python3 reply_monitor.py --sign "Your Name"
```

Categorises every reply (Interested / Not Interested / Question / Gone Quiet), writes a
suggested reply into `drafts/` for anything that needs one, and prints a morning summary.
**It never sends** — you approve and send each draft. Run it daily (cron or the
claude-code-remote scheduler) for the 9am check-in.

## Building a site when a deal closes (Job 6)

```bash
python3 build_site.py client.json      # see example_client.json for the shape
cd "Business Name" && netlify deploy --prod
```

Produces Home / Services / About / Gallery / Contact — mobile-first, fast, with the business
name + trade + area woven through every page for local SEO, and a Netlify-Forms contact form
that works the moment it's deployed. It runs its own quality check and fails loudly if
anything's missing.

## Pricing model (reference)
One-off build **£300–£800**, optional care plan **£30–£60/mo**. 5 builds/mo ≈ £2,000;
10 care plans ≈ £500/mo recurring.
