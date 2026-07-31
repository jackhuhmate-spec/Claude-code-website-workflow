import { sql } from "drizzle-orm";
import {
  boolean,
  doublePrecision,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";
import { createdAt, timestampTz, updatedAt } from "./columns.js";
import { contactKindEnum, discoverySourceEnum, suppressionReasonEnum } from "./enums.js";

/**
 * A real-world business. One row per business, whatever it becomes to us later — a lead, a
 * customer, or a record of somebody who told us to go away.
 *
 * Deliberately separate from `leads`: a business is a fact about the world, a lead is our
 * commercial relationship with it. Merging them makes it impossible to re-approach next
 * year without either losing the history or duplicating the business.
 */
export const businesses = pgTable(
  "businesses",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    name: text("name").notNull(),
    /** Lower-cased, punctuation-stripped name. A dedupe key, not a display value. */
    nameNormalised: text("name_normalised").notNull(),
    trade: text("trade"),
    area: text("area"),
    postcode: text("postcode"),
    address: text("address"),
    websiteUrl: text("website_url"),
    /** Registrable host of `websiteUrl`, for spotting two listings of one business. */
    websiteHost: text("website_host"),
    latitude: doublePrecision("latitude"),
    longitude: doublePrecision("longitude"),

    source: discoverySourceEnum("source").notNull(),
    /** Identifier at the source, e.g. an OSM node id. Makes re-imports idempotent. */
    sourceRef: text("source_ref"),

    /**
     * Chains and franchises are out of scope and must be excluded by name and by URL.
     * Stored rather than recomputed, so an existing exclusion cannot be silently lost
     * when the matching heuristic changes.
     */
    isChain: boolean("is_chain").notNull().default(false),

    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    // Partial: most sources supply a stable ref, but a manual entry has none and several
    // nulls must not collide.
    uniqueIndex("businesses_source_ref_uq")
      .on(t.source, t.sourceRef)
      .where(sql`source_ref is not null`),
    index("businesses_name_normalised_idx").on(t.nameNormalised),
    index("businesses_website_host_idx").on(t.websiteHost),
    index("businesses_area_idx").on(t.area),
  ],
);

/**
 * A way to reach a business. Its own table because a business may have several, they
 * arrive from different sources with different confidence, and an unverified one must stay
 * distinguishable from a verified one — invariant 1, never fabricate data.
 */
export const contacts = pgTable(
  "contacts",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    businessId: uuid("business_id")
      .notNull()
      .references(() => businesses.id, { onDelete: "cascade" }),
    kind: contactKindEnum("kind").notNull(),
    /** As found, for display and for auditing what was actually observed. */
    value: text("value").notNull(),
    /** Lower-cased address, or digits-only phone. The comparison key. */
    valueNormalised: text("value_normalised").notNull(),
    /** e.g. "owner", "info". Left null when unknown rather than guessed. */
    role: text("role"),
    /**
     * Whether the address plausibly belongs to this business rather than to its web
     * designer, a directory or a franchisor. Scraping produces all four.
     */
    isPlausible: boolean("is_plausible").notNull().default(true),
    source: discoverySourceEnum("source").notNull(),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    uniqueIndex("contacts_business_value_uq").on(t.businessId, t.kind, t.valueNormalised),
    // One address may legitimately front several businesses; we still need to find it.
    index("contacts_value_normalised_idx").on(t.kind, t.valueNormalised),
  ],
);

/**
 * The suppression list. Invariant 6: opt-outs are permanent and honoured everywhere.
 *
 * Keyed on the normalised value rather than on a business, because the party who opted out
 * is the address. If it later appears under a different business name the suppression must
 * still bite — exactly the case a per-lead flag would miss.
 *
 * Rows are never deleted. Suppression is not a preference to be re-litigated.
 */
export const suppressions = pgTable(
  "suppressions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    kind: contactKindEnum("kind").notNull(),
    valueNormalised: text("value_normalised").notNull(),
    reason: suppressionReasonEnum("reason").notNull(),
    /** Wording from the request itself, as evidence if it is ever challenged. */
    note: text("note"),
    /** Provenance: a reply message id, an import, a named human. */
    source: text("source"),
    suppressedAt: timestampTz("suppressed_at").notNull().defaultNow(),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("suppressions_kind_value_uq").on(t.kind, t.valueNormalised)],
);

/**
 * The audited result of looking at a business's live website: what was actually observed,
 * never what was assumed. The evidence behind every opening line we send.
 */
export const siteAudits = pgTable(
  "site_audits",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    businessId: uuid("business_id")
      .notNull()
      .references(() => businesses.id, { onDelete: "cascade" }),
    auditedAt: timestampTz("audited_at").notNull().defaultNow(),
    url: text("url"),
    /** 0–10. Null when the site could not be fetched, which is itself a finding. */
    score: integer("score"),
    biggestFlaw: text("biggest_flaw"),
    /** Individual observations: https, mobile, performance, a11y, seo, staleness. */
    findings: jsonb("findings").notNull().default({}),
    createdAt: createdAt(),
  },
  (t) => [index("site_audits_business_idx").on(t.businessId, t.auditedAt)],
);
