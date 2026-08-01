import { leads, messages, normaliseEmail } from "@agency/db";
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
 * `followups_log.csv` — the day 3/7/14 chaser touches.
 *
 * `touch` is the sequence position and is what stops a lead being chased a fourth time, so
 * it is carried onto both the message and the lead rather than recomputed by counting rows.
 */
export function followUpExternalId(email: string, touch: number): string {
  return `csv:followup:${email}:${String(touch)}`;
}

const MAX_TOUCH = 3;

export async function importFollowUpsLog(
  ctx: ImportContext,
  text: string,
): Promise<SourceReport> {
  const table = parseCsvTable(text);
  const stats = emptyStats();
  const problems = new ProblemLog();

  for (const record of table.records) {
    const name = record.get("business");
    const rawEmail = record.get("email");
    const touch = Number(record.get("touch"));
    const sentAt = parseCsvDate(record.get("date"));

    if (name === "" || rawEmail === "" || sentAt === null) {
      stats.skipped += 1;
      problems.add(
        record.line,
        "a follow-up row is missing its business, address or date",
      );
      continue;
    }
    if (!Number.isInteger(touch) || touch < 1 || touch > MAX_TOUCH) {
      stats.skipped += 1;
      problems.add(
        record.line,
        `touch ${record.get("touch")} is outside the 1-3 sequence`,
      );
      continue;
    }

    const email = normaliseEmail(rawEmail);
    const externalId = followUpExternalId(email, touch);

    const existing = await ctx.db
      .select({ id: messages.id })
      .from(messages)
      .where(eq(messages.externalId, externalId))
      .limit(1);

    if (existing.length > 0) {
      stats.unchanged += 1;
      continue;
    }

    // Resolved by address first: this file carries no area, so name-only keying would match
    // nothing already imported from `leads.csv` and fork every chased business into a
    // duplicate. Only when the address is unknown or shared does the name key apply.
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
      direction: "outbound",
      status: "sent",
      externalId,
      fromAddress: ctx.senderAddress,
      toAddress: email,
      body: "",
      touch,
      template: "csv_import_followup",
      sentAt,
    });
    stats.inserted += 1;

    await recordTouch(ctx, leadId, touch, sentAt);
  }

  return {
    source: "followups_log.csv",
    rows: table.records.length,
    stats,
    problems: problems.list(),
    problemCount: problems.count,
  };
}

async function recordTouch(
  ctx: ImportContext,
  leadId: string,
  touch: number,
  sentAt: Date,
): Promise<void> {
  const existing = await ctx.db
    .select({
      id: leads.id,
      status: leads.status,
      followUpsSent: leads.followUpsSent,
      lastContactedAt: leads.lastContactedAt,
    })
    .from(leads)
    .where(eq(leads.id, leadId))
    .limit(1);

  const lead = existing[0];
  if (lead === undefined) {
    return;
  }

  const changes = changedFields(lead, {
    // Highest touch wins: rows may arrive in any order, and a lower one must not undo a
    // higher one and license a fourth chase.
    followUpsSent: Math.max(lead.followUpsSent, touch),
    lastContactedAt:
      lead.lastContactedAt === null || sentAt > lead.lastContactedAt
        ? sentAt
        : lead.lastContactedAt,
    ...(lead.status === "new" || lead.status === "contacted"
      ? { status: "following_up" as const }
      : {}),
  });

  if (hasChanges(changes)) {
    await ctx.db
      .update(leads)
      .set({ ...changes, updatedAt: new Date() })
      .where(eq(leads.id, leadId));
  }
}
