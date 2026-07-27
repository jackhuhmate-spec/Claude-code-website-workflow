# System status — all green

Last verified: 2026-07-27

| Component | Status | Detail |
|---|---|---|
| Gmail SMTP | ✅ | Sends from jackhuhmate@gmail.com |
| Gmail IMAP | ✅ | Reads inbox, filters vendor noise |
| Netlify | ✅ | Deploys live, 2 sites up |
| GitHub push | ✅ | Private repo, token auth working |
| Repo privacy | 🔒 | Private — 121 leads no longer public |

## Live now
- `preview-bromley-roofer-ltd-d6fb37.netlify.app` — mockup for the hot lead
- Branch: `claude/tradesman-web-sales-machine-4wozz5` (default)

## Pipeline
```
leads          121
sent            85
replies          1   ← Bromley Roofer Ltd, INTERESTED, awaiting price
opted out        0
paused        False
```

## Run it

```bash
cp ops/.env.example ops/.env    # fill in creds, gitignored
./ops/env.sh python3 ops/run_cycle.py replies    # draft mode
./ops/env.sh python3 ops/run_cycle.py replies --auto   # send for real
./ops/env.sh python3 ops/run_cycle.py outreach --auto  # daily cold batch
./ops/env.sh python3 ops/run_cycle.py status
```

Or just message the agent: "check replies" / "send today's outreach".

## Kill switch
```bash
touch PAUSED     # stops all cold sending instantly
rm PAUSED        # resume
```

## Open item
One hot lead unanswered since 26 Jul — Bromley Roofer Ltd asked for a price.
Draft ready in `triage/`. Preview site is live to send with it.
