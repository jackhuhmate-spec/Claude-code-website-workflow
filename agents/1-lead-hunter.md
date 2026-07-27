# Agent 1 — Lead Hunter

**Runs:** daily, start of the outreach cycle.
**Invoke:** "Run the lead hunter" (optionally: "…for South London", "…find 20").
**Needs:** web search + fetch. No credentials.
**Touches:** reads `leads.csv`, `sent_log.csv`, `do_not_contact.csv` → appends to `leads.csv`.

## Job
Produce **verified** rows for `leads.csv`. Nothing else. Never emails anyone.

## Target
Independent / small (<10 staff) **London** businesses. No chains, no franchises, no agencies, nobody who already has a good modern site.

- **Group B** — no website at all (Facebook page, Google listing, or nothing).
- **Group A** — has a site scoring **under 7/10**.

Trades (plumber, electrician, roofer, builder, painter, plasterer, carpenter, tiler, landscaper, handyman, locksmith, gas engineer…) and local services (salons, barbers, cafés, restaurants, garages, gyms, groomers, cleaners, florists, clinics…).

## Steps
1. Read all of `leads.csv`, `sent_log.csv`, `do_not_contact.csv`. Never output a business, domain, phone or email already in any of them.
2. Search borough + trade ("plumber Peckham", "barber Tooting"). Rotate boroughs each run — log which ones in the report so the next run picks different ones.
3. **Actually fetch the homepage** before judging it. Can't load it → drop the lead. No exceptions.
4. Score 1–10: mobile/responsive, load speed, visual age, phone visible above the fold, HTTPS, stale content (old copyright, "coming soon", broken images), service clarity. Keep only 1–6.
5. Write **one concrete flaw**, 1–2 sentences, describing what you actually saw. "The footer copyright is frozen at 2021 and the homepage is padded with a keyword-stuffed brand list" — good. "Looks outdated" — rejected, rewrite it.
6. Contact details only from the business's own site or Google listing. Prefer `info@`, `hello@`, or the owner's address.

## Hard rules
- **Never fabricate.** Unverified field = **blank**. A blank email is fine — the sender skips it and it goes to `contact_form_messages.md`.
- Skip anything in `do_not_contact.csv`, permanently.
- Skip `no-reply@`, `@wixpress`, directory-scraped and shared-inbox-of-a-chain addresses.
- Dedupe on name, domain, phone and email.
- 15–30 usable leads per run. A shaky lead is worse than no lead.

## Output
Append to `leads.csv`, exact column order, quoting any field with a comma:

`Business Name,Trade,London Area,Phone,Email,Website,Website Score,Biggest Flaw,Group`

Group B rows: empty Website and Website Score.

## Report back
New leads count · A/B split · how many have an email · boroughs covered · what was rejected and why.
