import {
  index,
  integer,
  jsonb,
  pgTable,
  text,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";
import { businesses } from "./businesses.js";
import { createdAt, timestampTz, updatedAt } from "./columns.js";
import {
  deploymentKindEnum,
  deploymentStateEnum,
  projectStatusEnum,
  revisionStatusEnum,
} from "./enums.js";
import { leads } from "./sales.js";

/** A business that has bought. Separate from `leads` so the sales history survives. */
export const customers = pgTable(
  "customers",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    businessId: uuid("business_id")
      .notNull()
      .references(() => businesses.id, { onDelete: "restrict" }),
    leadId: uuid("lead_id").references(() => leads.id, { onDelete: "set null" }),
    /** Who we actually deal with. */
    contactName: text("contact_name"),
    billingEmail: text("billing_email"),
    wonAt: timestampTz("won_at").notNull().defaultNow(),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [uniqueIndex("customers_business_uq").on(t.businessId)],
);

/** A unit of delivered work for a customer: normally one website build. */
export const projects = pgTable(
  "projects",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    customerId: uuid("customer_id")
      .notNull()
      .references(() => customers.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    status: projectStatusEnum("status").notNull().default("briefing"),
    /**
     * The requirements intake: services, pages, imagery, booking, branding, inspiration.
     * Held as JSON because the brief genuinely varies per customer, and a column per
     * question would be schema churn for no query benefit.
     */
    brief: jsonb("brief").notNull().default({}),
    dueAt: timestampTz("due_at"),
    deliveredAt: timestampTz("delivered_at"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    index("projects_customer_idx").on(t.customerId),
    index("projects_status_idx").on(t.status),
  ],
);

/** The website being built for a project. One live site per project. */
export const websites = pgTable(
  "websites",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    /** URL-safe identifier, and the Netlify site name stem. */
    slug: text("slug").notNull(),
    /** Which template family produced it. Two customers must not get the same site. */
    template: text("template").notNull(),
    /** Colours, fonts, logo and spacing decisions, resolved once and reused. */
    brandTokens: jsonb("brand_tokens").notNull().default({}),
    repoUrl: text("repo_url"),
    customDomain: text("custom_domain"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    uniqueIndex("websites_slug_uq").on(t.slug),
    index("websites_project_idx").on(t.projectId),
  ],
);

/**
 * One generated version of a website. Revisions are the customer feedback loop, so they
 * are numbered and never overwritten: "go back to the one before" must be answerable.
 */
export const revisions = pgTable(
  "revisions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    websiteId: uuid("website_id")
      .notNull()
      .references(() => websites.id, { onDelete: "cascade" }),
    /** 1-based, contiguous per website. */
    number: integer("number").notNull(),
    status: revisionStatusEnum("status").notNull().default("draft"),
    /** The resolved content model the generator rendered from. */
    content: jsonb("content").notNull().default({}),
    /** Verbatim customer feedback that prompted this revision. */
    requestedChanges: text("requested_changes"),
    approvedAt: timestampTz("approved_at"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [uniqueIndex("revisions_website_number_uq").on(t.websiteId, t.number)],
);

/**
 * A push of one revision to a host.
 *
 * `kind` separates `preview` from `final`, and that distinction is load-bearing:
 * invariant 9 forbids deploying a final site for an unpaid lead, and the cleanup job that
 * retires old previews must never touch a paid customer's live site.
 */
export const deployments = pgTable(
  "deployments",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    websiteId: uuid("website_id")
      .notNull()
      .references(() => websites.id, { onDelete: "cascade" }),
    revisionId: uuid("revision_id")
      .notNull()
      .references(() => revisions.id, { onDelete: "restrict" }),
    kind: deploymentKindEnum("kind").notNull(),
    state: deploymentStateEnum("state").notNull().default("pending"),
    provider: text("provider").notNull().default("netlify"),
    /** Provider's site id, needed to redeploy or retire it later. */
    providerSiteId: text("provider_site_id"),
    providerDeployId: text("provider_deploy_id"),
    url: text("url"),
    /** Set only once the deployed URL has been fetched and checked, not on API success. */
    verifiedAt: timestampTz("verified_at"),
    deployedAt: timestampTz("deployed_at"),
    retiredAt: timestampTz("retired_at"),
    error: text("error"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    index("deployments_website_idx").on(t.websiteId, t.createdAt),
    index("deployments_state_idx").on(t.state),
    uniqueIndex("deployments_provider_deploy_uq").on(t.provider, t.providerDeployId),
  ],
);
