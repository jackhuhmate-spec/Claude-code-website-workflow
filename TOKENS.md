# Getting your Netlify and GitHub tokens

## ✅ Gmail — DONE, tested, working

Your app password is live. Confirmed: SMTP OK, IMAP OK, 85 known recipients,
test email sent and received, 1 hot lead found.

---

## 1. Netlify token (Agent 5 — putting sites live)

Needed only to deploy. Agents 1–4 work without it.

1. Go to **https://app.netlify.com** and log in (sign up free if you haven't — no card needed).
2. Click your **avatar, top right** → **User settings**.
3. Left sidebar → **Applications**.
4. Scroll to **Personal access tokens** → click **New access token**.
5. Description: `website workflow`. Expiry: pick **No expiry** (or 1 year).
6. Click **Generate token**.
7. **Copy it now** — Netlify shows it exactly once. Starts with `nfp_`.

Paste it to me as:
```
NETLIFY_TOKEN=nfp_xxxxxxxxxxxxxxxx
```

Free tier gives 100GB bandwidth/month — plenty for client sites.

---

## 2. GitHub token (saving state back to the repo)

Only needed if you want `sent_log.csv`, `handled_messages.txt` etc. committed
automatically. Without it I keep state in the workspace and you copy it over.

1. Go to **https://github.com/settings/tokens?type=beta**
   (or: avatar → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**)
2. Click **Generate new token**.
3. **Token name:** `website workflow`
4. **Expiration:** 90 days (or custom — 1 year max)
5. **Repository access:** select **Only select repositories** →
   choose **`Claude-code-website-workflow`**.
   ⚠️ Do NOT pick "All repositories" — scope it to this one repo only.
6. **Permissions** → **Repository permissions** → find **Contents** →
   set the dropdown to **Read and write**.
   (Leave everything else as "No access". Contents is all that's needed.)
7. Scroll down → **Generate token**.
8. Copy it — shown once. Starts with `github_pat_`.

Paste it to me as:
```
GITHUB_TOKEN=github_pat_xxxxxxxxxxxxxxxx
```

---

## Revoking access, any time

| Credential | Revoke at |
|---|---|
| Gmail app password | myaccount.google.com/apppasswords → bin icon |
| Netlify token | User settings → Applications → Revoke |
| GitHub token | Settings → Developer settings → Fine-grained tokens → Delete |

Each one is instant and total.
