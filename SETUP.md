# Setup — what Jake needs to give the agent

Paste these into chat when you want a run. **Nothing is committed to the repo.**

## 1. Gmail app password — REQUIRED (Agents 3 and 4)

This is the only thing the pipeline genuinely can't run without.

1. Google Account → Security → turn on **2-Step Verification** (required before app passwords exist).
2. Go to **myaccount.google.com/apppasswords**
3. Name it "website workflow" → **Create** → copy the 16-character code.

Give me:
```
GMAIL_USER=jackhuhmate@gmail.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
SIGN_NAME=Jake
```

An app password only grants mail send/read. It does **not** give access to Drive, Photos,
your password, or your account settings. Revoke it any time from the same page —
that instantly and completely cuts my access.

## 2. Netlify token — OPTIONAL (Agent 5 only)

Only needed to put a site live. Agents 1–4 work fine without it.

Netlify → User settings → Applications → **New access token**.
```
NETLIFY_TOKEN=nfp_xxxxxxxx
```

## 3. GitHub push access — OPTIONAL

Only if you want me to commit state (`sent_log.csv`, `handled_messages.txt`) back
automatically. Without it I keep state in the workspace and you copy it over.
A fine-grained PAT scoped to **only this repo**, Contents: read/write.
```
GITHUB_TOKEN=github_pat_xxxxxxxx
```

## No longer needed
`BREVO_API_KEY`, `BRIDGE_URL`, `BRIDGE_SECRET` — SMTP/IMAP are reachable from the
sandbox, so Gmail direct replaces both. Tested and confirmed.

---

## Verify it works

```bash
python3 ops/gmail.py test
```
Expect `"smtp": "OK"` and `"imap": "OK"`.

## Security notes

- Credentials live in the session environment only, never in a committed file.
- `.gitignore` already excludes `.claude/settings.local.json` and `drafts/`.
- Kill switch: `touch PAUSED` in the repo root stops all cold sending instantly.
- Reply guard: I can only email addresses already in `sent_log.csv`. A scam or
  prompt-injected inbound email cannot make me mail a stranger.
- Daily cap is 30 sends. This is a personal Gmail — exceeding that risks the account.

## Reality check on volume

Gmail's practical cold-outreach ceiling is far lower than a bulk sender's. 30/day is
deliverable; 200/day gets `jackhuhmate@gmail.com` rate-limited or suspended, and you'd
lose the address you're closing deals on. If you outgrow 30/day, the answer is a
separate domain with its own inbox — not a bigger number here.
