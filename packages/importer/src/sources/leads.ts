import {
  businesses,
  contacts,
  leads,
  normaliseEmail,
  normaliseHost,
  normaliseName,
  normalisePhone,
  siteAudits,
} from "@agency/db";
import { and, eq } from "drizzle-orm";
import type { CsvRecord } from "../csv.js";
import { parseCsvTable } from "../csv.js";
import { changedFields, hasChanges } from "../diff.js";
import { businessSourceRef } from "../entities.js";
import type { ImportContext, SourceReport } from "../types.js";
import { ProblemLog, emptyStats } from "../types.js";

/**
 * `leads.csv` — the master list the Python machine works from.
 *
 * One row becomes up to five rows here: the business, its email and phone contacts, the
 * audit that produced the pitch, and the lead itself. That fan-out is the point of the
 * migration; the CSV flattens all five into one line, which is why a business cannot
 * currently hold two contacts or a second audit.
 */

interface ParsedLead {
  readonly name: string;
  readonly nameNormalised: string;
  readonly sourceRef: string;
  readonly trade: string | null;
  readonly area: string | null;
  readonly websiteUrl: string | null;
  readonly websiteHost: string | null;
  readonly email: string | null;
  readonly phone: string | null;
  readonly score: number | null;
  readonly biggestFlaw: string | null;
  readonly group: "A" | "B" | null;
}

function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/**
 * Deliberately conservative: an address is accepted only if it has the shape of one.
 * The alternative to rejecting a malformed value is emailing it.
 */
function plausibleEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function parseScore(value: string): number | null {
  if (value.trim() === "") {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 10) {
    return null;
  }
  return parsed;
}

function parseGroup(value: string): "A" | "B" | null {
  const upper = value.trim().toUpperCase();
  return upper === "A" || upper === "B" ? upper : null;
}

function parseRecord(record: CsvRecord): ParsedLead | null {
  const name = record.get("Business Name");
  if (name === "") {
    return null;
  }

  const nameNormalised = normaliseName(name);
  const area = blankToNull(record.get("London Area"));
  const website = record.get("Website");
  const email = record.get("Email");
  const phone = record.get("Phone");

  return {
    name,
    nameNormalised,
    // Area is part of the key: two unrelated firms can share a trading name across London,
    // and merging them would send one of them the other's audit.
    sourceRef: businessSourceRef(name, area),
    trade: blankToNull(record.get("Trade")),
    area,
    websiteUrl: blankToNull(website),
    websiteHost: website === "" ? null : normaliseHost(website),
    email: email !== "" && plausibleEmail(email) ? normaliseEmail(email) : null,
    phone: phone === "" ? null : normalisePhone(phone),
    score: parseScore(record.get("Website Score")),
    biggestFlaw: blankToNull(record.get("Biggest Flaw")),
    group: parseGroup(record.get("Group")),
  };
}

export async function importLeads(
  ctx: ImportContext,
  text: string,
): Promise<SourceReport> {
  const table = parseCsvTable(text);
  const stats = emptyStats();
  const problems = new ProblemLog();
  const seenRefs = new Set<string>();

  for (const record of table.records) {
    const parsed = parseRecord(record);
    if (parsed === null) {
      stats.skipped += 1;
      problems.add(record.line, "no business name");
      continue;
    }

    // A name repeated within one file is a duplicate row, not a second business. Importing
    // it twice would be caught by the unique index, but as a crash rather than a report.
    if (seenRefs.has(parsed.sourceRef)) {
      stats.skipped += 1;
      problems.add(record.line, `duplicate of an earlier row (${parsed.name})`);
      continue;
    }
    seenRefs.add(parsed.sourceRef);

    const businessId = await upsertBusiness(ctx, parsed, stats);
    await upsertContacts(ctx, businessId, parsed);
    await upsertAudit(ctx, businessId, parsed);
    await upsertLead(ctx, businessId, parsed);
  }

  return {
    source: "leads.csv",
    rows: table.records.length,
    stats,
    problems: problems.list(),
    problemCount: problems.count,
  };
}

async function upsertBusiness(
  ctx: ImportContext,
  parsed: ParsedLead,
  stats: { inserted: number; updated: number; unchanged: number },
): Promise<string> {
  const existing = await ctx.db
    .select()
    .from(businesses)
    .where(
      and(
        eq(businesses.source, "csv_import"),
        eq(businesses.sourceRef, parsed.sourceRef),
      ),
    )
    .limit(1);

  const current = existing[0];
  const desired = {
    name: parsed.name,
    nameNormalised: parsed.nameNormalised,
    trade: parsed.trade,
    area: parsed.area,
    websiteUrl: parsed.websiteUrl,
    websiteHost: parsed.websiteHost,
  };

  if (current === undefined) {
    const inserted = await ctx.db
      .insert(businesses)
      .values({ ...desired, source: "csv_import", sourceRef: parsed.sourceRef })
      .returning({ id: businesses.id });
    stats.inserted += 1;
    const row = inserted[0];
    if (row === undefined) {
      throw new Error("insert returned no row");
    }
    return row.id;
  }

  const changes = changedFields(current, desired);
  if (hasChanges(changes)) {
    await ctx.db
      .update(businesses)
      .set({ ...changes, updatedAt: new Date() })
      .where(eq(businesses.id, current.id));
    stats.updated += 1;
  } else {
    stats.unchanged += 1;
  }
  return current.id;
}

async function upsertContacts(
  ctx: ImportContext,
  businessId: string,
  parsed: ParsedLead,
): Promise<void> {
  const wanted: { kind: "email" | "phone"; value: string; valueNormalised: string }[] =
    [];
  if (parsed.email !== null) {
    wanted.push({ kind: "email", value: parsed.email, valueNormalised: parsed.email });
  }
  if (parsed.phone !== null && parsed.phone !== "") {
    wanted.push({
      kind: "phone",
      value: parsed.phone,
      valueNormalised: parsed.phone,
    });
  }

  for (const contact of wanted) {
    const existing = await ctx.db
      .select({ id: contacts.id })
      .from(contacts)
      .where(
        and(
          eq(contacts.businessId, businessId),
          eq(contacts.kind, contact.kind),
          eq(contacts.valueNormalised, contact.valueNormalised),
        ),
      )
      .limit(1);

    if (existing.length === 0) {
      await ctx.db
        .insert(contacts)
        .values({ ...contact, businessId, source: "csv_import" });
    }
  }
}

/**
 * Audits are append-only history, so re-importing an unchanged row must not add a second
 * one — but a genuinely re-scored site should. Comparing the observation itself gives both.
 */
async function upsertAudit(
  ctx: ImportContext,
  businessId: string,
  parsed: ParsedLead,
): Promise<void> {
  if (parsed.score === null && parsed.biggestFlaw === null) {
    return;
  }

  const existing = await ctx.db
    .select({
      id: siteAudits.id,
      url: siteAudits.url,
      score: siteAudits.score,
      biggestFlaw: siteAudits.biggestFlaw,
    })
    .from(siteAudits)
    .where(eq(siteAudits.businessId, businessId));

  const alreadyRecorded = existing.some(
    (audit) =>
      audit.url === parsed.websiteUrl &&
      audit.score === parsed.score &&
      audit.biggestFlaw === parsed.biggestFlaw,
  );
  if (alreadyRecorded) {
    return;
  }

  await ctx.db.insert(siteAudits).values({
    businessId,
    url: parsed.websiteUrl,
    score: parsed.score,
    biggestFlaw: parsed.biggestFlaw,
  });
}

/**
 * The lead's own pipeline state is not the CSV's to set beyond creation.
 *
 * `status`, `nextActionAt` and `followUpsSent` are written from the send and reply logs and
 * later by the platform itself; refreshing them from `leads.csv` on every run would drag a
 * lead that has replied back to `new`.
 */
async function upsertLead(
  ctx: ImportContext,
  businessId: string,
  parsed: ParsedLead,
): Promise<void> {
  const existing = await ctx.db
    .select()
    .from(leads)
    .where(eq(leads.businessId, businessId))
    .limit(1);

  const current = existing[0];
  const desired = {
    group: parsed.group,
    score: parsed.score,
    biggestFlaw: parsed.biggestFlaw,
  };

  if (current === undefined) {
    await ctx.db.insert(leads).values({ businessId, ...desired });
    return;
  }

  const changes = changedFields(current, desired);
  if (hasChanges(changes)) {
    await ctx.db
      .update(leads)
      .set({ ...changes, updatedAt: new Date() })
      .where(eq(leads.id, current.id));
  }
}
