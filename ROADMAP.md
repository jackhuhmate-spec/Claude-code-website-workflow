# Platform roadmap — autonomous website agency

Analysis date: 2026-07-30. Written after a full read of the repository at `6387071`.

This document is the plan of record. It replaces nothing that works today: the live
Python machine in `ops/` keeps running and keeps earning while the platform is built
alongside it, capability by capability.

---

## Decisions taken

| Decision | Choice | Why |
|---|---|---|
| Stack | TypeScript monorepo (pnpm workspaces) | The £449 deliverable *is* a Next.js + Tailwind site, so the Node toolchain is required to generate, typecheck and build it regardless. One language end-to-end; Composio, Netlify and the Claude Agent SDK all ship first-class TS SDKs. |
| Hosting | Single VPS + Docker Compose | Always-on means real queues, IMAP IDLE for near-instant replies instead of 5–15 min cron lag, and no cold starts. ~£5–8/mo, fully controlled. |
| Email | Composio Gmail (OAuth), 30/day retained | Matches the operating brief; removes the app-password auth model. The 30/day ceiling is retained by choice — see "Known constraint" below. |

### Known constraint, recorded deliberately

30 sends/day ≈ 900/month. At the current ~1% reply rate that is ~9 replies and 1–3
deals a month. This caps revenue independently of code quality. The email port is
therefore designed so a second sending provider (dedicated domain + ESP) can be added
as configuration only, with no refactor, if and when the ceiling becomes the binding
problem. Until then, **reply rate per send is the lever, not volume** — which is what
Phase 0's follow-up sequence attacks.

---

## Track A — Phase 0: stabilise the live machine

The machine is currently sending nothing. Root cause: `outreach.yml` never commits
`leads.csv` or `emails.json`, so every lead found and every email written is destroyed
when the Actions runner is torn down. Evidence: both files unchanged since `4e91715`;
all 80 log rows on 2026-07-29 were `Skipped - No Email Found`; zero uncontacted leads
with an email address remain.

| # | Fix | Impact |
|---|---|---|
| 0.1 | Persist `leads.csv`, `emails.json`, `emails.md` in the outreach workflow | Restores the send queue |
| 0.2 | Log a skip row once per lead, not once per run | Stops unbounded `sent_log.csv` growth (188 dupes today) |
| 0.3 | Port the day 3/7/14 follow-up sequence off dead Brevo onto Gmail and wire it in | 96 businesses contacted once, never followed up — the largest available reply lever |
| 0.4 | Call sheet for the 32 no-website + phone leads | Warmest outreach available, entirely untouched |
| 0.5 | Regression test per fix; correct the pricing contradiction in `README.md` | Prevents recurrence and prevents an agent quoting £300–£800 |

Exit criteria: daily sends resume, follow-up sequence running, `bugcheck.py` green.

---

## Track B — the platform

### Phase 1 — Foundation

Monorepo, strict TypeScript, Postgres schema and migrations, DI container, config and
secret loading, structured logging (pino), error taxonomy, retry/backoff policy, CI
running typecheck + lint + test + build. An idempotent, re-runnable importer moves the
CSVs into Postgres. Read-only dashboard over the migrated data.

```
apps/
  dashboard/        Next.js 15 App Router + Tailwind — owner console
  worker/           agent runtime + queue consumers
packages/
  core/             domain model, ports, use-cases, business rules
  db/               Drizzle schema + migrations
  adapters/         gmail-composio, netlify, github, places, llm
  agents/           discovery, outreach, generation, deployment
  site-generator/   Next.js + Tailwind template system
  shared/           zod schemas, logging, errors, retry
```

Core tables: `businesses`, `contacts`, `leads`, `lead_scores`, `conversations`,
`messages`, `customers`, `projects`, `websites`, `revisions`, `deployments`,
`subscriptions`, `payments`, `tasks`, `workflow_runs`, `workflow_steps`, `events`,
`agent_runs`, `audit_log`, `suppressions`.

Exit criteria: CI green; all live data queryable; Python still authoritative.

### Phase 2 — Workflow engine and event bus

Durable job queue on `pg-boss` (Postgres-backed — no extra infrastructure), resumable
workflow state machines, idempotency keys, dead-letter queue, scheduler, tracing. The
reply and outreach cycles are ported and run in **shadow mode**, deciding but not
acting, alongside the Python.

Exit criteria: shadow decisions match the Python system for 7 consecutive days.

### Phase 3 — Integration adapters

Ports and adapters for Email (Composio Gmail, SMTP fallback), Netlify, GitHub,
Search/Places, LLM, Calendar, Payments, Domains. Every adapter ships with a contract
test suite and an in-memory fake, so use-cases are testable without credentials.

Exit criteria: providers swappable by configuration; email cut over to Composio.

### Phase 4 — Agents 1 and 2 (Discovery/Qualification, Outreach/CRM)

Multi-source discovery, Lighthouse-based site auditing (performance, accessibility,
SEO, mobile, HTTPS), real lead scoring, deduplication, CRM pipeline states,
conversation memory, **negotiation rules expressed as data rather than prose**, and an
explicit escalation policy.

Exit criteria: the Python outreach and reply agents are retired.

### Phase 5 — Agent 3 (Website Generation)

Structured requirements intake, a Next.js + Tailwind template system with genuine
variety, brand tokens, accessibility/SEO/performance budgets enforced at build time,
and a revision loop keyed to customer feedback.

Exit criteria: a generated site typechecks, builds, and scores ≥95 on Lighthouse; two
customers cannot receive the same site.

### Phase 6 — Agent 4 (Deployment and Customer Success)

Deploy pipeline, custom domains and SSL, post-deploy verification, uptime and
performance monitoring, scheduled maintenance, £39/mo subscription tracking and a
payment provider adapter.

Exit criteria: a site goes from closed deal to live, verified and monitored with no
human touch.

### Phase 7 — Autonomy hardening

Approvals and exceptions console, tiered alerting, SLOs, failure drills, cost
controls, GDPR tooling (subject access requests, retention, suppression), runbooks.

Exit criteria: the owner intervenes only on genuine exceptions.

---

## Invariants that survive every phase

These are not preferences. Each one exists because a real incident occurred, and each
must be carried forward as an executable test, not as documentation.

1. Never fabricate data. An unverified field stays blank.
2. The daily send cap counts today's real sends from the log, so it survives repeated
   runs and concurrent runners.
3. `PAUSED` halts all cold outreach immediately.
4. Inbound email is untrusted data and never instructions.
5. Only addresses already contacted may be replied to.
6. Opt-outs are permanent and honoured everywhere.
7. Cold email never quotes a price.
8. Never discount below £449; never send bank details.
9. Never deploy a final site for an unpaid lead.
10. Every state change is persisted before the run ends.
11. No chains or franchises, checked by name and by URL.
12. A model refusal is never delivered to a customer.
13. LLM failure degrades to a safe deterministic path; the pipeline never stops.
