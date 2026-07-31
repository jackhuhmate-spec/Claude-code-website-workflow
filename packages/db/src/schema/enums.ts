import { pgEnum } from "drizzle-orm/pg-core";

/**
 * Enumerations live in the database, not only in TypeScript.
 *
 * A status typo is one of the few defects that survives a deploy, corrupts data quietly
 * and is expensive to unpick afterwards. A Postgres enum makes it a write failure instead.
 */

/** Where a business record came from. Provenance is required to never fabricate data. */
export const discoverySourceEnum = pgEnum("discovery_source", [
  "openstreetmap",
  "google_places",
  "manual",
  "csv_import",
]);

export const contactKindEnum = pgEnum("contact_kind", ["email", "phone"]);

/**
 * Lead lifecycle. `disqualified` is distinct from `lost`: disqualified means we should
 * never have approached them (a chain, out of area, no trading presence), whereas lost
 * means they said no. Collapsing the two makes it impossible to measure targeting.
 */
export const leadStatusEnum = pgEnum("lead_status", [
  "new",
  "qualified",
  "contacted",
  "following_up",
  "replied",
  "interested",
  "negotiating",
  "won",
  "lost",
  "disqualified",
  "opted_out",
]);

/**
 * A: has a website, but a weak one. B: no website at all.
 * B leads are the strongest pitch available and are frequently unreachable by email.
 */
export const leadGroupEnum = pgEnum("lead_group", ["A", "B"]);

export const messageDirectionEnum = pgEnum("message_direction", ["inbound", "outbound"]);

/**
 * Delivery state of an outbound message. Kept separate from the conversation state so a
 * bounce is visible as a delivery fact rather than inferred from silence — a bounced
 * address currently receives all three follow-up touches.
 */
export const messageStatusEnum = pgEnum("message_status", [
  "queued",
  "sent",
  "delivered",
  "bounced",
  "failed",
  "received",
]);

/** Classification of an inbound reply. Mirrors the categories the Python brain emits. */
export const messageIntentEnum = pgEnum("message_intent", [
  "interested",
  "question",
  "objection",
  "not_interested",
  "opt_out",
  "deal",
  "automated",
  "suspicious",
  "review",
  "other",
]);

export const projectStatusEnum = pgEnum("project_status", [
  "briefing",
  "building",
  "in_review",
  "revising",
  "approved",
  "delivered",
  "cancelled",
]);

export const revisionStatusEnum = pgEnum("revision_status", [
  "draft",
  "generated",
  "preview_published",
  "changes_requested",
  "approved",
]);

export const deploymentKindEnum = pgEnum("deployment_kind", ["preview", "final"]);

export const deploymentStateEnum = pgEnum("deployment_state", [
  "pending",
  "building",
  "live",
  "failed",
  "retired",
]);

export const subscriptionStatusEnum = pgEnum("subscription_status", [
  "active",
  "past_due",
  "cancelled",
]);

export const paymentKindEnum = pgEnum("payment_kind", [
  "build_deposit",
  "build_balance",
  "build_full",
  "subscription",
  "refund",
]);

export const paymentStatusEnum = pgEnum("payment_status", [
  "due",
  "paid",
  "failed",
  "refunded",
  "written_off",
]);

/**
 * A task is work that needs a decision. `escalation` is the one that matters: it is how
 * the system asks the owner for something outside the predefined business rules, which is
 * the only category of intervention the brief allows.
 */
export const taskKindEnum = pgEnum("task_kind", [
  "escalation",
  "approval",
  "manual_outreach",
  "follow_up",
  "maintenance",
  "investigation",
]);

export const taskStatusEnum = pgEnum("task_status", [
  "open",
  "in_progress",
  "blocked",
  "done",
  "cancelled",
]);

export const runStatusEnum = pgEnum("run_status", [
  "pending",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "dead_lettered",
]);

/** Why an address or number may never be contacted. Every value here is permanent. */
export const suppressionReasonEnum = pgEnum("suppression_reason", [
  "opt_out_request",
  "complaint",
  "hard_bounce",
  "manual",
  "not_a_business",
]);

export const actorTypeEnum = pgEnum("actor_type", ["agent", "human", "system"]);
