import {
  businesses,
  contacts,
  conversations,
  leads,
  normaliseHost,
  normaliseName,
} from "@agency/db";
import { ValidationError } from "@agency/shared";
import { and, eq } from "drizzle-orm";
import type { ImportContext } from "./types.js";

/**
 * Shared resolution of the business → lead → conversation chain.
 *
 * All four source files describe the same businesses from different angles, and each one
 * must land on the same rows. Deriving the key in one place is what guarantees that:
 * if `sent_log.csv` computed its reference even slightly differently from `leads.csv`, the
 * import would silently create a parallel set of businesses and every history would attach
 * to the wrong one.
 */

export const CSV_SOURCE_PREFIX = "leads";

/** Stable business key: normalised name and area, which is all every file carries. */
export function businessSourceRef(name: string, area: string | null): string {
  const areaPart = area === null || area.trim() === "" ? "" : normaliseName(area);
  return `${CSV_SOURCE_PREFIX}:${normaliseName(name)}|${areaPart}`;
}

export interface BusinessSeed {
  readonly name: string;
  readonly area: string | null;
  readonly trade?: string | null;
  readonly websiteUrl?: string | null;
}

/**
 * The business for a row, created if the logs mention someone `leads.csv` no longer does.
 *
 * That happens: the send log is 361 rows against a 159-row master list, because leads are
 * pruned while their history stays. Dropping those rows would lose the record of having
 * emailed a real person — including, potentially, one who then opted out.
 */
export async function findOrCreateBusiness(
  ctx: ImportContext,
  seed: BusinessSeed,
): Promise<string> {
  const sourceRef = businessSourceRef(seed.name, seed.area);

  const existing = await ctx.db
    .select({ id: businesses.id })
    .from(businesses)
    .where(and(eq(businesses.source, "csv_import"), eq(businesses.sourceRef, sourceRef)))
    .limit(1);

  const current = existing[0];
  if (current !== undefined) {
    return current.id;
  }

  const website = seed.websiteUrl ?? null;
  const inserted = await ctx.db
    .insert(businesses)
    .values({
      name: seed.name,
      nameNormalised: normaliseName(seed.name),
      trade: seed.trade ?? null,
      area: seed.area,
      websiteUrl: website,
      websiteHost: website === null ? null : normaliseHost(website),
      source: "csv_import",
      sourceRef,
    })
    .returning({ id: businesses.id });

  return requireRow(inserted).id;
}

export async function findOrCreateLead(
  ctx: ImportContext,
  businessId: string,
): Promise<string> {
  const existing = await ctx.db
    .select({ id: leads.id })
    .from(leads)
    .where(eq(leads.businessId, businessId))
    .limit(1);

  const current = existing[0];
  if (current !== undefined) {
    return current.id;
  }

  const inserted = await ctx.db
    .insert(leads)
    .values({ businessId })
    .returning({ id: leads.id });
  return requireRow(inserted).id;
}

/**
 * How confidently an email address identifies a business.
 *
 * `contacts` is unique on (business, kind, value), not on value alone, so one address may
 * legitimately belong to two businesses — a shared agency inbox, or a sole trader operating
 * under two names. Picking the first match would attach one firm's history to the other, so
 * ambiguity is a distinct outcome the caller reports rather than a silent choice.
 */
export type EmailResolution =
  | { readonly kind: "unique"; readonly businessId: string }
  | { readonly kind: "none" }
  | { readonly kind: "ambiguous" };

export async function resolveBusinessByEmail(
  ctx: ImportContext,
  emailNormalised: string,
): Promise<EmailResolution> {
  const matches = await ctx.db
    .selectDistinct({ businessId: contacts.businessId })
    .from(contacts)
    .where(and(eq(contacts.kind, "email"), eq(contacts.valueNormalised, emailNormalised)))
    .limit(2);

  if (matches.length > 1) {
    return { kind: "ambiguous" };
  }
  const only = matches[0];
  return only === undefined
    ? { kind: "none" }
    : { kind: "unique", businessId: only.businessId };
}

export interface ResolvedBusiness {
  readonly businessId: string;
  readonly resolution: EmailResolution["kind"];
}

/**
 * The business a log row refers to, by address first and name second.
 *
 * This ordering is load-bearing. `followups_log.csv` and `replies_log.csv` carry a business
 * name but no area, while `leads.csv` keys on name *and* area: resolving those logs by name
 * alone would match nothing and fork every chased business into a duplicate, leaving the
 * follow-up history on a shadow copy of the lead. The address is the reliable identifier
 * because it is precisely what was emailed.
 *
 * Falling through to the name is still necessary — the logs outlive pruned leads — so a row
 * for an address we no longer hold creates the business rather than being dropped.
 */
export async function resolveBusinessForEmail(
  ctx: ImportContext,
  emailNormalised: string,
  seed: BusinessSeed,
): Promise<ResolvedBusiness> {
  const resolved = await resolveBusinessByEmail(ctx, emailNormalised);
  if (resolved.kind === "unique") {
    return { businessId: resolved.businessId, resolution: "unique" };
  }
  return {
    businessId: await findOrCreateBusiness(ctx, seed),
    resolution: resolved.kind,
  };
}

/** The email contact for a business, if we hold one — used to attach a conversation. */
export async function findContactId(
  ctx: ImportContext,
  businessId: string,
  emailNormalised: string,
): Promise<string | null> {
  const existing = await ctx.db
    .select({ id: contacts.id })
    .from(contacts)
    .where(
      and(
        eq(contacts.businessId, businessId),
        eq(contacts.kind, "email"),
        eq(contacts.valueNormalised, emailNormalised),
      ),
    )
    .limit(1);

  return existing[0]?.id ?? null;
}

/**
 * One email conversation per lead.
 *
 * The CSVs carry no thread identifier, so there is nothing to distinguish two threads with
 * the same business. Collapsing them into one conversation is the honest reading of the
 * available data; real threading starts when messages arrive through the Gmail adapter with
 * their provider thread ids.
 */
export async function findOrCreateConversation(
  ctx: ImportContext,
  leadId: string,
  contactId: string | null,
  subject: string | null,
): Promise<string> {
  const existing = await ctx.db
    .select({ id: conversations.id })
    .from(conversations)
    .where(and(eq(conversations.leadId, leadId), eq(conversations.channel, "email")))
    .limit(1);

  const current = existing[0];
  if (current !== undefined) {
    return current.id;
  }

  const inserted = await ctx.db
    .insert(conversations)
    .values({ leadId, contactId, channel: "email", subject })
    .returning({ id: conversations.id });

  return requireRow(inserted).id;
}

/**
 * The CSVs record a calendar date, never a time.
 *
 * Midnight UTC is a deliberate, documented approximation rather than a guess at when the
 * email actually went out — anything else would invent precision the source does not have.
 */
export function parseCsvDate(value: string): Date | null {
  const trimmed = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return null;
  }
  const parsed = new Date(`${trimmed}T00:00:00.000Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function requireRow<T>(rows: T[]): T {
  const row = rows[0];
  if (row === undefined) {
    throw new ValidationError(
      "importer.insert_returned_nothing",
      "insert returned no row",
    );
  }
  return row;
}
