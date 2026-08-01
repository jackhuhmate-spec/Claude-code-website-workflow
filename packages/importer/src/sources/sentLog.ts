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
 * `sent_log.csv` — every attempt to contact a business, sent or not.
 *
 * Only rows with status `Sent` become messages. The rest ("Skipped - No Email Found",
 * "Opted Out", "Skipped - No Copy Written") are records of a decision not to send, and
 * turning them into outbound messages would overstate what the business has received —
 * the file currently holds seventy skip rows for a single day.
 */
const SENT_STATUS = "sent";

/**
 * Idempotency key. The CSV has no provider message id, so one is derived from the facts it
 * does have: who it went to and on what day. The daily cap makes a second send to the same
 * address on the same day impossible, so this is unique in practice.
 */
export function sentExternalId(email: string, date: string): string {
  return `csv:sent:${email}:${date}`;
}

export async function importSentLog(
  ctx: ImportContext,
  text: string,
): Promise<SourceReport> {
  const table = parseCsvTable(text);
  const stats = emptyStats();
  const problems = new ProblemLog();

  for (const record of table.records) {
    const status = record.get("Status").trim().toLowerCase();
    if (status !== SENT_STATUS) {
      stats.ignored += 1;
      continue;
    }

    const name = record.get("Business Name");
    const rawEmail = record.get("Email");
    const dateText = record.get("Date Sent");
    const sentAt = parseCsvDate(dateText);

    if (name === "" || rawEmail === "" || sentAt === null) {
      stats.skipped += 1;
      problems.add(record.line, "a sent row is missing its business, address or date");
      continue;
    }

    const email = normaliseEmail(rawEmail);
    const externalId = sentExternalId(email, dateText.trim());

    const existing = await ctx.db
      .select({ id: messages.id })
      .from(messages)
      .where(eq(messages.externalId, externalId))
      .limit(1);

    if (existing.length > 0) {
      stats.unchanged += 1;
      continue;
    }

    const area = record.get("London Area");
    // Address first, name+area second — the same resolution the other log files use, so a
    // difference in how an area is spelled between the two files cannot fork a business.
    const resolved = await resolveBusinessForEmail(ctx, email, {
      name,
      area: area === "" ? null : area,
      trade: record.get("Trade") || null,
      websiteUrl: record.get("Website") || null,
    });
    if (resolved.resolution === "ambiguous") {
      problems.add(
        record.line,
        `${email} belongs to more than one business; keyed on name`,
      );
    }
    const businessId = resolved.businessId;
    const leadId = await findOrCreateLead(ctx, businessId);
    const contactId = await findContactId(ctx, businessId, email);
    const subject = record.get("Email Subject");
    const conversationId = await findOrCreateConversation(
      ctx,
      leadId,
      contactId,
      subject === "" ? null : subject,
    );

    await ctx.db.insert(messages).values({
      conversationId,
      direction: "outbound",
      status: "sent",
      externalId,
      fromAddress: ctx.senderAddress,
      toAddress: email,
      subject: subject === "" ? null : subject,
      // The CSV logs that a send happened, never what was said. Inventing a body would be
      // fabricating evidence of what a real person was told.
      body: "",
      touch: 0,
      template: "csv_import",
      sentAt,
    });
    stats.inserted += 1;

    await advanceContactDates(ctx, leadId, sentAt);
  }

  return {
    source: "sent_log.csv",
    rows: table.records.length,
    stats,
    problems: problems.list(),
    problemCount: problems.count,
  };
}

/**
 * Keep the lead's contact window in step with its messages.
 *
 * Rows arrive in file order, not date order, so both ends are widened rather than assigned:
 * a later row carrying an earlier date must not move `firstContactedAt` forwards.
 */
async function advanceContactDates(
  ctx: ImportContext,
  leadId: string,
  sentAt: Date,
): Promise<void> {
  const existing = await ctx.db
    .select({
      id: leads.id,
      status: leads.status,
      firstContactedAt: leads.firstContactedAt,
      lastContactedAt: leads.lastContactedAt,
    })
    .from(leads)
    .where(eq(leads.id, leadId))
    .limit(1);

  const lead = existing[0];
  if (lead === undefined) {
    return;
  }

  const first =
    lead.firstContactedAt === null || sentAt < lead.firstContactedAt
      ? sentAt
      : lead.firstContactedAt;
  const last =
    lead.lastContactedAt === null || sentAt > lead.lastContactedAt
      ? sentAt
      : lead.lastContactedAt;

  const changes = changedFields(lead, {
    firstContactedAt: first,
    lastContactedAt: last,
    // Only promote out of `new`. A lead that has since replied or been won must not be
    // dragged back to `contacted` by re-importing its history.
    ...(lead.status === "new" ? { status: "contacted" as const } : {}),
  });

  if (hasChanges(changes)) {
    await ctx.db
      .update(leads)
      .set({ ...changes, updatedAt: new Date() })
      .where(eq(leads.id, leadId));
  }
}
