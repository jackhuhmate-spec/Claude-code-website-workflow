import {
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";
import { businesses, contacts } from "./businesses.js";
import { createdAt, timestampTz, updatedAt } from "./columns.js";
import {
  leadGroupEnum,
  leadStatusEnum,
  messageDirectionEnum,
  messageIntentEnum,
  messageStatusEnum,
} from "./enums.js";

/**
 * A commercial opportunity with a business. One open lead per business.
 *
 * `status` is the pipeline; `nextActionAt` is what makes the pipeline run without a human
 * reading it. A lead nobody is scheduled to touch is a lead that quietly dies — which is
 * how 96 businesses ended up contacted once and never chased.
 */
export const leads = pgTable(
  "leads",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    businessId: uuid("business_id")
      .notNull()
      .references(() => businesses.id, { onDelete: "cascade" }),
    status: leadStatusEnum("status").notNull().default("new"),
    group: leadGroupEnum("group"),
    /** Latest score, denormalised from `leadScores` for cheap sorting. */
    score: integer("score"),
    /** The verified flaw the pitch leads with. Null when nothing was observed. */
    biggestFlaw: text("biggest_flaw"),
    /** Why this lead was disqualified or lost. Required to measure targeting. */
    outcomeReason: text("outcome_reason"),

    firstContactedAt: timestampTz("first_contacted_at"),
    lastContactedAt: timestampTz("last_contacted_at"),
    lastRepliedAt: timestampTz("last_replied_at"),
    /** When the next automated touch is due. Null means nothing is scheduled. */
    nextActionAt: timestampTz("next_action_at"),
    /** How many follow-up touches have been sent. The day 3/7/14 sequence position. */
    followUpsSent: integer("follow_ups_sent").notNull().default(0),

    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    uniqueIndex("leads_business_uq").on(t.businessId),
    index("leads_status_idx").on(t.status),
    // The work queue: "what is due, oldest first".
    index("leads_next_action_idx").on(t.nextActionAt),
  ],
);

/**
 * Every score a lead has been given, with the breakdown that produced it.
 *
 * Append-only. Keeping the history is what allows a scoring change to be evaluated against
 * outcomes rather than argued about — the alternative is overwriting the only evidence of
 * whether the previous model was better.
 */
export const leadScores = pgTable(
  "lead_scores",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    leadId: uuid("lead_id")
      .notNull()
      .references(() => leads.id, { onDelete: "cascade" }),
    score: integer("score").notNull(),
    /** Per-signal contributions, so a score is explainable after the fact. */
    breakdown: jsonb("breakdown").notNull().default({}),
    /** Identifier of the scoring rules that produced this, e.g. "heuristic-v2". */
    scorerVersion: text("scorer_version").notNull(),
    scoredAt: timestampTz("scored_at").notNull().defaultNow(),
    createdAt: createdAt(),
  },
  (t) => [index("lead_scores_lead_idx").on(t.leadId, t.scoredAt)],
);

/**
 * An email thread with one contact at one business.
 *
 * `externalThreadId` is the provider's thread identifier. It is what lets a reply be
 * matched to its conversation rather than guessed at from the subject line.
 */
export const conversations = pgTable(
  "conversations",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    leadId: uuid("lead_id")
      .notNull()
      .references(() => leads.id, { onDelete: "cascade" }),
    contactId: uuid("contact_id").references(() => contacts.id, { onDelete: "set null" }),
    channel: text("channel").notNull().default("email"),
    externalThreadId: text("external_thread_id"),
    subject: text("subject"),
    lastMessageAt: timestampTz("last_message_at"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    index("conversations_lead_idx").on(t.leadId),
    uniqueIndex("conversations_external_thread_uq").on(t.channel, t.externalThreadId),
  ],
);

/**
 * One email, in or out.
 *
 * `externalId` carries the provider's message id and is unique, which is what makes reply
 * handling idempotent: processing the same message twice must not produce a second reply.
 * The Python system solved this with an append-only `handled_messages.txt`; here the
 * constraint is the database's job.
 *
 * `intentConfidence` is stored because a low-confidence classification must be escalated
 * to a human rather than acted on — the existing rule is below 70 goes to review.
 */
export const messages = pgTable(
  "messages",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    conversationId: uuid("conversation_id")
      .notNull()
      .references(() => conversations.id, { onDelete: "cascade" }),
    direction: messageDirectionEnum("direction").notNull(),
    status: messageStatusEnum("status").notNull(),
    /** Provider message id. Unique per channel; the idempotency key for replies. */
    externalId: text("external_id"),
    fromAddress: text("from_address").notNull(),
    toAddress: text("to_address").notNull(),
    subject: text("subject"),
    body: text("body").notNull(),

    /** Which follow-up touch this was: 0 for the first cold email, 1–3 for chasers. */
    touch: integer("touch"),
    /** Template or generator that produced it, for measuring copy against replies. */
    template: text("template"),
    /** False when a human wrote or approved it. */
    isAutomated: boolean("is_automated").notNull().default(true),

    intent: messageIntentEnum("intent"),
    /** 0–100. Below the escalation threshold the system must not act unaided. */
    intentConfidence: integer("intent_confidence"),

    sentAt: timestampTz("sent_at"),
    receivedAt: timestampTz("received_at"),
    /** Set when the provider confirms a permanent failure. Stops all further touches. */
    failedAt: timestampTz("failed_at"),
    failureReason: text("failure_reason"),

    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("messages_external_id_uq").on(t.externalId),
    index("messages_conversation_idx").on(t.conversationId, t.createdAt),
    index("messages_direction_status_idx").on(t.direction, t.status),
  ],
);
