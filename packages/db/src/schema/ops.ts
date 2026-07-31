import { sql } from "drizzle-orm";
import {
  index,
  integer,
  jsonb,
  pgTable,
  text,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";
import { createdAt, timestampTz, updatedAt } from "./columns.js";
import { actorTypeEnum, runStatusEnum, taskKindEnum, taskStatusEnum } from "./enums.js";

/**
 * Work that needs a decision — including the escalations that are the only interventions
 * the owner should ever see. A task is the system saying "this is outside my rules".
 */
export const tasks = pgTable(
  "tasks",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    kind: taskKindEnum("kind").notNull(),
    status: taskStatusEnum("status").notNull().default("open"),
    /** 1 highest. Drives what the owner is shown first. */
    priority: integer("priority").notNull().default(3),
    subject: text("subject").notNull(),
    detail: text("detail"),
    /** What the task is about: a lead, a message, a deployment. */
    entityType: text("entity_type"),
    entityId: uuid("entity_id"),
    /** Everything needed to action it without opening another system. */
    payload: jsonb("payload").notNull().default({}),
    assignedTo: text("assigned_to"),
    dueAt: timestampTz("due_at"),
    resolvedAt: timestampTz("resolved_at"),
    resolution: text("resolution"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    index("tasks_status_priority_idx").on(t.status, t.priority, t.createdAt),
    index("tasks_entity_idx").on(t.entityType, t.entityId),
  ],
);

/**
 * One execution of a named workflow.
 *
 * `idempotencyKey` is unique and is the whole point: a workflow re-triggered by a retry, a
 * duplicate webhook or a second runner must join the existing run rather than start a
 * parallel one. Without it, "send today's batch" running twice sends twice.
 */
export const workflowRuns = pgTable(
  "workflow_runs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    workflow: text("workflow").notNull(),
    /** Stable per logical execution, e.g. `outreach:2026-07-31`. */
    idempotencyKey: text("idempotency_key").notNull(),
    status: runStatusEnum("status").notNull().default("pending"),
    input: jsonb("input").notNull().default({}),
    output: jsonb("output"),
    error: jsonb("error"),
    attempt: integer("attempt").notNull().default(1),
    startedAt: timestampTz("started_at"),
    finishedAt: timestampTz("finished_at"),
    /** Set when a run is picked up, so an abandoned run is detectable. */
    heartbeatAt: timestampTz("heartbeat_at"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    uniqueIndex("workflow_runs_idempotency_uq").on(t.workflow, t.idempotencyKey),
    index("workflow_runs_status_idx").on(t.status, t.createdAt),
  ],
);

/**
 * A single step within a run. This is what makes a workflow resumable: on restart, steps
 * already recorded `succeeded` are skipped rather than re-executed.
 *
 * That matters most for steps with side effects outside the database. Re-running "send the
 * email" after a crash is not a retry, it is a second email to a real person.
 */
export const workflowSteps = pgTable(
  "workflow_steps",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    runId: uuid("run_id")
      .notNull()
      .references(() => workflowRuns.id, { onDelete: "cascade" }),
    /** Stable name, unique within the run — the resume key. */
    name: text("name").notNull(),
    sequence: integer("sequence").notNull(),
    status: runStatusEnum("status").notNull().default("pending"),
    input: jsonb("input").notNull().default({}),
    output: jsonb("output"),
    error: jsonb("error"),
    attempt: integer("attempt").notNull().default(1),
    startedAt: timestampTz("started_at"),
    finishedAt: timestampTz("finished_at"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    uniqueIndex("workflow_steps_run_name_uq").on(t.runId, t.name),
    index("workflow_steps_run_seq_idx").on(t.runId, t.sequence),
  ],
);

/**
 * The event log and outbox.
 *
 * Events are written in the same transaction as the state change that caused them, then
 * published separately. That ordering is what stops the classic failure where a row is
 * committed and the notification is lost because the process died in between.
 *
 * `dedupeKey` makes republishing safe.
 */
export const events = pgTable(
  "events",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    type: text("type").notNull(),
    aggregateType: text("aggregate_type").notNull(),
    aggregateId: uuid("aggregate_id"),
    payload: jsonb("payload").notNull().default({}),
    dedupeKey: text("dedupe_key"),
    occurredAt: timestampTz("occurred_at").notNull().defaultNow(),
    /** Null until a consumer has taken it. The outbox queue is `where published_at is null`. */
    publishedAt: timestampTz("published_at"),
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("events_dedupe_key_uq").on(t.dedupeKey),
    // Partial index: the unpublished tail stays small even as the log grows unbounded.
    index("events_unpublished_idx")
      .on(t.occurredAt)
      .where(sql`published_at is null`),
    index("events_aggregate_idx").on(t.aggregateType, t.aggregateId),
  ],
);

/**
 * One invocation of an agent, with what it cost and whether it had to fall back.
 *
 * `fallbackUsed` is the important column. Invariant 13 requires LLM failure to degrade to a
 * deterministic path rather than stop the pipeline, and a silent permanent fallback looks
 * identical to a healthy system from the outside — until the copy quality collapses.
 */
export const agentRuns = pgTable(
  "agent_runs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    agent: text("agent").notNull(),
    runId: uuid("run_id").references(() => workflowRuns.id, { onDelete: "set null" }),
    model: text("model"),
    status: runStatusEnum("status").notNull().default("pending"),
    promptTokens: integer("prompt_tokens"),
    completionTokens: integer("completion_tokens"),
    /** Tenths of a penny, integer, so cost never accumulates floating-point drift. */
    costTenthPence: integer("cost_tenth_pence"),
    latencyMs: integer("latency_ms"),
    fallbackUsed: text("fallback_used"),
    error: jsonb("error"),
    startedAt: timestampTz("started_at"),
    finishedAt: timestampTz("finished_at"),
    createdAt: createdAt(),
  },
  (t) => [
    index("agent_runs_agent_idx").on(t.agent, t.createdAt),
    index("agent_runs_run_idx").on(t.runId),
  ],
);

/**
 * Who changed what, and why.
 *
 * The brief requires every action to be logged. In an autonomous system that is not
 * bureaucracy: when an agent emails the wrong person or agrees to something it should not
 * have, this table is the only way to reconstruct which decision produced it.
 */
export const auditLog = pgTable(
  "audit_log",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    actorType: actorTypeEnum("actor_type").notNull(),
    /** Agent name, human identifier, or the process that acted. */
    actor: text("actor").notNull(),
    action: text("action").notNull(),
    entityType: text("entity_type").notNull(),
    entityId: uuid("entity_id"),
    /** Only the fields that changed, never a whole-row copy. */
    before: jsonb("before"),
    after: jsonb("after"),
    reason: text("reason"),
    occurredAt: timestampTz("occurred_at").notNull().defaultNow(),
    createdAt: createdAt(),
  },
  (t) => [
    index("audit_log_entity_idx").on(t.entityType, t.entityId, t.occurredAt),
    index("audit_log_actor_idx").on(t.actor, t.occurredAt),
  ],
);
