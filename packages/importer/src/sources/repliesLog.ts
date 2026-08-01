import { events, leads, messages, normaliseEmail } from "@agency/db";
import { eq } from "drizzle-orm";
import { parseCsvTable } from "../csv.js";
import { changedFields, hasChanges } from "../diff.js";
import {
  findContactId,
  findOrCreateConversation,
  findOrCreateLead,
  parseCsvDate,
  resolveBusinessForEmail,
} from "../entities.js";
import type { ImportContext, SourceReport } from "../types.js";
import { ProblemLog, emptyStats } from "../types.js";

/**
 * `replies_log.csv` — what came back, and what the machine did about it.
 *
 * A row is evidence of two separate things: an inbound email with a classification, and a
 * decision the system took in response. They are stored separately because only the first
 * is a message. The `action` column summarises the reply that was sent ("Auto-replied with
 * price") without preserving its text, so recording it as an outbound message would invent
 * the contents of an email a real business actually received.
 */
export function replyExternalId(email: string, date: string): string {
  return `csv:reply:${email}:${date}`;
}

export function replyActionDedupeKey(email: string, date: string): string {
  return `csv:reply-action:${email}:${date}`;
}

type Intent =
  | "interested"
  | "question"
  | "objection"
  | "not_interested"
  | "opt_out"
  | "deal"
  | "automated"
  | "suspicious"
  | "review"
  | "other";

/**
 * The Python brain's categories, mapped onto the stored enum.
 *
 * Both spellings of each are accepted because the file spans changes to the classifier —
 * it holds `Interested` and `OBJECTION` on adjacent lines. An unrecognised category becomes
 * `other` and is reported: quietly discarding it would lose the fact that a human replied.
 */
const INTENT_BY_CATEGORY = new Map<string, Intent>([
  ["deal", "deal"],
  ["interested", "interested"],
  ["question", "question"],
  ["objection", "objection"],
  ["optout", "opt_out"],
  ["opt_out", "opt_out"],
  ["not_interested", "not_interested"],
  ["auto", "automated"],
  ["automated", "automated"],
  ["suspicious", "suspicious"],
  ["review", "review"],
]);

type LeadStatus =
  | "new"
  | "qualified"
  | "contacted"
  | "following_up"
  | "replied"
  | "interested"
  | "negotiating"
  | "won"
  | "lost"
  | "disqualified"
  | "opted_out";

/**
 * How far through the pipeline a status is.
 *
 * Rows are not in date order and a lead may already have moved on, so a reply only ever
 * moves a lead forwards. Without this, importing an old "Question" over a lead that has
 * since been won would reopen a closed sale.
 */
const STATUS_RANK: Readonly<Record<LeadStatus, number>> = {
  new: 0,
  qualified: 1,
  contacted: 2,
  following_up: 3,
  replied: 4,
  interested: 5,
  negotiating: 6,
  won: 7,
  lost: 7,
  disqualified: 7,
  opted_out: 8,
};

/** Terminal outcomes an import must never overwrite, whatever a later row says. */
const SETTLED: ReadonlySet<LeadStatus> = new Set<LeadStatus>([
  "won",
  "lost",
  "disqualified",
  "opted_out",
]);

function statusForIntent(intent: Intent): LeadStatus {
  switch (intent) {
    case "opt_out":
      return "opted_out";
    case "deal":
      return "negotiating";
    case "interested":
      return "interested";
    // A question, an objection or an automated bounce-back are all still just a reply. None
    // of them is evidence of buying intent, and promoting on them would inflate the pipeline.
    default:
      return "replied";
  }
}

/**
 * The name column sometimes holds a raw `From` header — `Farrants Flooring <info@…>`.
 * Only the display part is a business name; the address is captured separately.
 */
function cleanBusinessName(value: string): string {
  return value.replace(/<[^>]*>/g, "").trim();
}

export async function importRepliesLog(
  ctx: ImportContext,
  text: string,
): Promise<SourceReport> {
  const table = parseCsvTable(text);
  const stats = emptyStats();
  const problems = new ProblemLog();

  for (const record of table.records) {
    const name = cleanBusinessName(record.get("business"));
    const rawEmail = record.get("email");
    const dateText = record.get("date").trim();
    const repliedAt = parseCsvDate(dateText);

    if (name === "" || rawEmail === "" || repliedAt === null) {
      stats.skipped += 1;
      problems.add(record.line, "a reply row is missing its business, address or date");
      continue;
    }

    const email = normaliseEmail(rawEmail);
    const category = record.get("category").trim().toLowerCase();
    const intent = INTENT_BY_CATEGORY.get(category) ?? "other";
    if (intent === "other" && category !== "" && category !== "other") {
      problems.add(record.line, `unrecognised category "${record.get("category")}"`);
    }

    const externalId = replyExternalId(email, dateText);
    const existing = await ctx.db
      .select({ id: messages.id })
      .from(messages)
      .where(eq(messages.externalId, externalId))
      .limit(1);

    if (existing.length > 0) {
      stats.unchanged += 1;
      continue;
    }

    const resolved = await resolveBusinessForEmail(ctx, email, { name, area: null });
    if (resolved.resolution === "ambiguous") {
      problems.add(
        record.line,
        `${email} belongs to more than one business; keyed on name`,
      );
    }
    const leadId = await findOrCreateLead(ctx, resolved.businessId);
    const contactId = await findContactId(ctx, resolved.businessId, email);
    const conversationId = await findOrCreateConversation(ctx, leadId, contactId, null);

    await ctx.db.insert(messages).values({
      conversationId,
      direction: "inbound",
      status: "received",
      externalId,
      fromAddress: email,
      toAddress: ctx.senderAddress,
      // The log records that they replied and how it was classified, never the words. An
      // empty body is the truthful representation of a message we no longer hold.
      body: "",
      isAutomated: false,
      intent,
      receivedAt: repliedAt,
    });
    stats.inserted += 1;

    await recordAction(ctx, leadId, email, dateText, record.get("action"), category);
    await advanceOnReply(ctx, leadId, repliedAt, intent);
  }

  return {
    source: "replies_log.csv",
    rows: table.records.length,
    stats,
    problems: problems.list(),
    problemCount: problems.count,
  };
}

/**
 * What the machine did in response, as an audit event rather than a message.
 *
 * `publishedAt` is set on insert, which matters more than it looks: the outbox queue is
 * `where published_at is null`, so leaving it unset would hand every historic auto-reply to
 * the consumers as new work and re-email businesses about a conversation from last month.
 * Imported history is a record, not an instruction.
 */
async function recordAction(
  ctx: ImportContext,
  leadId: string,
  email: string,
  date: string,
  action: string,
  category: string,
): Promise<void> {
  const summary = action.trim();
  if (summary === "") {
    return;
  }

  const now = new Date();
  await ctx.db
    .insert(events)
    .values({
      type: "reply.handled",
      aggregateType: "lead",
      aggregateId: leadId,
      payload: { action: summary, category, email, source: "replies_log.csv" },
      dedupeKey: replyActionDedupeKey(email, date),
      occurredAt: now,
      publishedAt: now,
    })
    .onConflictDoNothing({ target: events.dedupeKey });
}

async function advanceOnReply(
  ctx: ImportContext,
  leadId: string,
  repliedAt: Date,
  intent: Intent,
): Promise<void> {
  const existing = await ctx.db
    .select({
      id: leads.id,
      status: leads.status,
      lastRepliedAt: leads.lastRepliedAt,
      nextActionAt: leads.nextActionAt,
    })
    .from(leads)
    .where(eq(leads.id, leadId))
    .limit(1);

  const lead = existing[0];
  if (lead === undefined) {
    return;
  }

  const proposed = statusForIntent(intent);
  const current = lead.status;
  // An opt-out is the one transition allowed to override a settled lead, because it is a
  // legal instruction rather than a pipeline opinion.
  const mayAdvance =
    proposed === "opted_out" ||
    (!SETTLED.has(current) && STATUS_RANK[proposed] > STATUS_RANK[current]);

  const changes = changedFields(lead, {
    lastRepliedAt:
      lead.lastRepliedAt === null || repliedAt > lead.lastRepliedAt
        ? repliedAt
        : lead.lastRepliedAt,
    // Someone who replied is not owed an automated chase; the thread is a human's now.
    nextActionAt: null,
    ...(mayAdvance ? { status: proposed } : {}),
  });

  if (hasChanges(changes)) {
    await ctx.db
      .update(leads)
      .set({ ...changes, updatedAt: new Date() })
      .where(eq(leads.id, leadId));
  }
}
