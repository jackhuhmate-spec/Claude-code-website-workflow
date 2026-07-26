# runs/ — daily work archive

Every automated run saves its full working record here so nothing is lost and
everything is auditable. Structure:

```
runs/
  2026-07-27/
    agents/
      north.json        # raw verified-lead JSON returned by each research agent
      east.json
      south.json
      west.json
    summary.md          # what the lead-gen run found, added, and sent that day
    replies.md          # what the reply run read, auto-answered, and escalated
```

A one-line-per-run index is also kept in `../run_history.csv`
(date, run_type, new_leads, emails_sent, replies_handled, notes).

Nothing here is deleted — it's the permanent record of the machine's activity.
