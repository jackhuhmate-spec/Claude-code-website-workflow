# Going 24/7 — hands-off setup

**Time: about 10 minutes, once. After that you do nothing.**

GitHub Actions runs the agents on GitHub's servers, on a schedule. Your laptop can be
off. It's free for private repos up to 2,000 minutes/month — this uses roughly 400.

---

## Step 1 — Add your secrets to GitHub

Go to:
**https://github.com/jackhuhmate-spec/Claude-code-website-workflow/settings/secrets/actions**

Click **New repository secret** and add these five, one at a time:

| Name | Value |
|---|---|
| `GMAIL_USER` | `jackhuhmate@gmail.com` |
| `GMAIL_APP_PASSWORD` | your 16-char Gmail app password |
| `SIGN_NAME` | `Jack` |
| `GROQ_API_KEY` | your Groq API key (free at console.groq.com) |
| `NETLIFY_TOKEN` | your `nfp_…` Netlify token |

Secrets are encrypted. They never appear in logs, and nobody can read them back — not
even you. GitHub masks them automatically if a script tries to print one.

---

## Step 2 — Let the workflow files in

GitHub blocks any personal access token from uploading workflow files. This is a
deliberate security rule — a stolen token otherwise means stolen CI. So I can't push
these three files myself. Pick either option:

### Option A — give the token workflow scope (30 seconds, then I do the rest)

1. **https://github.com/settings/tokens?type=beta** → click your token
2. **Repository permissions** → find **Workflows** → set to **Read and write**
3. **Update token**
4. Tell me "done" — I'll push the workflows immediately.

### Option B — upload them yourself (no permission change)

In your repo, click **Add file → Create new file**, and make each of these three.
The filename box needs the full path, exactly:

- `.github/workflows/replies.yml`
- `.github/workflows/outreach.yml`
- `.github/workflows/healthcheck.yml`

Copy the contents from the matching files in `.github/workflows/` in your workspace.

---

## Step 3 — Turn Actions on

Repo → **Actions** tab → if prompted, click **I understand my workflows, go ahead and enable them**.

Then, before trusting it unattended, do one manual run:

**Actions** → **Reply agent (hourly)** → **Run workflow** → set *auto* to **false** →
**Run workflow**. That's a dry run — it drafts but sends nothing. Check the log looks right.

---

## What then happens, forever, without you

| When | What |
|---|---|
| **Every hour** | Reads inbox, categorises replies, answers as Jack, logs opt-outs, commits state |
| **Every hour, if a deal appears** | Emails you "HOT LEAD - action needed" with the message |
| **09:00 UTC daily** | Sends up to 30 cold emails, archives the run |
| **Monday 08:00 UTC** | Full bug check, emails you the result |

You get an email only when there's a **deal** or a **breakage**. Otherwise silence.

---

## Controls

| Action | How |
|---|---|
| **Stop everything now** | Create a file called `PAUSED` in the repo root. Delete it to resume. |
| Stop just cold outreach | Actions → Outreach agent → ⋯ → Disable workflow |
| Run something right now | Actions → pick workflow → Run workflow |
| See what happened | Actions tab — every run is logged |
| Revoke all access | Delete the Gmail app password at myaccount.google.com/apppasswords |

---

## Honest limitations

- **Hourly, not instant.** GitHub cron fires roughly on the hour and can lag 5–15
  minutes when their queues are busy. A reply might wait up to ~75 minutes. For cold
  outreach that's completely fine — nobody expects a reply in 30 seconds. True instant
  delivery needs a always-on server with an IMAP IDLE connection, which costs money and
  breaks more often. Hourly is the right trade.
- **GitHub disables cron on inactive repos** after 60 days with no commits. The agents
  commit state constantly, so this won't trigger — but if you ever see it stop, push
  anything to wake it.
- **The reply copy is template-based.** It handles price questions, objections and
  opt-outs well. Anything unusual gets flagged to you rather than guessed at — by design.
  You still make the actual decisions on deals.
- **30 emails/day cap.** This is your personal Gmail. Going higher risks the account
  that your deals live in.
