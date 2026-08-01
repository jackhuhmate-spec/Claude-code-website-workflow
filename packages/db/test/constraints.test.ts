import { and, eq, isNull, sql } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  BUILD_PRICE_PENCE,
  CARE_PLAN_PENCE_PER_MONTH,
  businesses,
  contacts,
  conversations,
  customers,
  events,
  leads,
  messages,
  subscriptions,
  suppressions,
  workflowRuns,
  workflowSteps,
} from "../src/schema/index.js";
import { createTestDatabase } from "../src/testing/harness.js";
import type { TestDatabase, TestDatabaseHandle } from "../src/testing/harness.js";

/**
 * These tests exist because the invariants they cover are enforced by the database, not by
 * application code. A unique index that was never proved to bite is indistinguishable from
 * a comment, and each one here corresponds to a way the current Python system has failed or
 * could fail: a second email to someone who opted out, a duplicate reply, a resumed
 * workflow re-sending a step it already completed.
 */

function first<T>(rows: T[]): T {
  const row = rows[0];
  if (row === undefined) {
    throw new Error("expected at least one row");
  }
  return row;
}

/**
 * Drizzle wraps driver failures, so the Postgres detail — including the constraint name —
 * is on `cause`, not on the top-level message. Flattening the chain lets each test name the
 * exact index it expects to fire, rather than settling for "something went wrong".
 */
function flattenError(error: unknown): string {
  const parts: string[] = [];
  let current: unknown = error;
  for (let depth = 0; current instanceof Error && depth < 5; depth += 1) {
    const detailed = current as Error & { constraint?: unknown; detail?: unknown };
    parts.push(current.message);
    if (typeof detailed.constraint === "string") parts.push(detailed.constraint);
    if (typeof detailed.detail === "string") parts.push(detailed.detail);
    current = current.cause;
  }
  return parts.join(" | ");
}

/** Assert that a write was refused, and refused by the constraint we meant. */
async function expectRejectedBy(
  operation: Promise<unknown>,
  constraint: string,
): Promise<void> {
  let caught: unknown;
  let rejected = false;
  try {
    await operation;
  } catch (error) {
    caught = error;
    rejected = true;
  }

  expect(rejected, `expected the write to be refused by ${constraint}`).toBe(true);
  expect(flattenError(caught)).toContain(constraint);
}

let handle: TestDatabaseHandle;
let db: TestDatabase;

beforeAll(async () => {
  handle = await createTestDatabase();
  db = handle.db;
});

afterAll(async () => {
  await handle.close();
});

async function insertBusiness(name: string, sourceRef?: string): Promise<string> {
  const rows = await db
    .insert(businesses)
    .values({
      name,
      nameNormalised: name.toLowerCase(),
      source: "openstreetmap",
      ...(sourceRef === undefined ? {} : { sourceRef }),
    })
    .returning({ id: businesses.id });
  return first(rows).id;
}

describe("suppressions", () => {
  it("cannot hold the same address twice", async () => {
    await db.insert(suppressions).values({
      kind: "email",
      valueNormalised: "stop@example.com",
      reason: "opt_out_request",
    });

    await expectRejectedBy(
      db.insert(suppressions).values({
        kind: "email",
        valueNormalised: "stop@example.com",
        reason: "complaint",
      }),
      "suppressions_kind_value_uq",
    );
  });

  it("keys on the value, so the same address under a new business is still suppressed", async () => {
    // The party who opted out is the address. A per-lead flag would miss this entirely,
    // and re-mailing them is a PECR breach, not a bug report.
    await db.insert(suppressions).values({
      kind: "email",
      valueNormalised: "shared@example.com",
      reason: "opt_out_request",
    });

    const found = await db
      .select()
      .from(suppressions)
      .where(
        and(
          eq(suppressions.kind, "email"),
          eq(suppressions.valueNormalised, "shared@example.com"),
        ),
      );

    expect(found).toHaveLength(1);
  });

  it("separates an email from a phone number with the same text", async () => {
    await db
      .insert(suppressions)
      .values({ kind: "phone", valueNormalised: "07000000000", reason: "manual" });

    await expect(
      db
        .insert(suppressions)
        .values({ kind: "email", valueNormalised: "07000000000", reason: "manual" }),
    ).resolves.not.toThrow();
  });
});

describe("businesses", () => {
  it("rejects a second import of the same source record", async () => {
    await insertBusiness("Acme Plumbing", "osm/node/1");

    await expectRejectedBy(
      insertBusiness("Acme Plumbing Ltd", "osm/node/1"),
      "businesses_source_ref_uq",
    );
  });

  it("allows many manually-entered businesses with no source reference", async () => {
    // A partial index: nulls are not duplicates of each other, or the second hand-added
    // business would be refused.
    await insertBusiness("Hand Added One");
    await expect(insertBusiness("Hand Added Two")).resolves.toBeTruthy();
  });
});

describe("contacts", () => {
  it("deduplicates an address within one business but allows it across businesses", async () => {
    const a = await insertBusiness("Contact Co A", "osm/node/10");
    const b = await insertBusiness("Contact Co B", "osm/node/11");

    await db.insert(contacts).values({
      businessId: a,
      kind: "email",
      value: "Info@Example.com",
      valueNormalised: "info@example.com",
      source: "openstreetmap",
    });

    await expectRejectedBy(
      db.insert(contacts).values({
        businessId: a,
        kind: "email",
        value: "info@example.com",
        valueNormalised: "info@example.com",
        source: "csv_import",
      }),
      "contacts_business_value_uq",
    );

    await expect(
      db.insert(contacts).values({
        businessId: b,
        kind: "email",
        value: "info@example.com",
        valueNormalised: "info@example.com",
        source: "csv_import",
      }),
    ).resolves.toBeTruthy();
  });
});

describe("leads", () => {
  it("holds one lead per business", async () => {
    const businessId = await insertBusiness("One Lead Ltd", "osm/node/20");
    await db.insert(leads).values({ businessId });

    await expectRejectedBy(db.insert(leads).values({ businessId }), "leads_business_uq");
  });

  it("refuses a status that is not in the lifecycle", async () => {
    // Raw SQL because TypeScript already prevents this at compile time; the point is that
    // the database refuses it too, for anything writing outside the type system.
    await expectRejectedBy(
      db.execute(sql`update leads set status = 'archived' where false`),
      "invalid input value for enum",
    );
  });

  it("exposes a due-work queue via next_action_at", async () => {
    const businessId = await insertBusiness("Due Soon Ltd", "osm/node/21");
    const due = new Date("2026-07-01T09:00:00.000Z");
    await db.insert(leads).values({ businessId, nextActionAt: due, status: "contacted" });

    const rows = await db
      .select({ nextActionAt: leads.nextActionAt })
      .from(leads)
      .where(eq(leads.businessId, businessId));

    // Round-tripped as an instant, not as a wall-clock string.
    expect(first(rows).nextActionAt).toEqual(due);
  });
});

describe("messages", () => {
  async function insertConversation(name: string, ref: string): Promise<string> {
    const businessId = await insertBusiness(name, ref);
    const leadRows = await db
      .insert(leads)
      .values({ businessId })
      .returning({ id: leads.id });
    const rows = await db
      .insert(conversations)
      .values({ leadId: first(leadRows).id })
      .returning({ id: conversations.id });
    return first(rows).id;
  }

  it("cannot record the same provider message twice", async () => {
    // This replaces `handled_messages.txt`. Processing an inbound message twice means
    // sending a second reply to a real person.
    const conversationId = await insertConversation("Reply Co", "osm/node/30");
    const values = {
      conversationId,
      direction: "inbound" as const,
      status: "received" as const,
      externalId: "<abc@mail.gmail.com>",
      fromAddress: "owner@example.com",
      toAddress: "jackhuhmate@gmail.com",
      body: "sounds good",
    };

    await db.insert(messages).values(values);
    await expectRejectedBy(db.insert(messages).values(values), "messages_external_id_uq");
  });

  it("allows many messages with no provider id yet", async () => {
    // Queued outbound mail has no external id until the provider accepts it.
    const conversationId = await insertConversation("Queued Co", "osm/node/31");
    const values = {
      conversationId,
      direction: "outbound" as const,
      status: "queued" as const,
      fromAddress: "jackhuhmate@gmail.com",
      toAddress: "owner@example.com",
      body: "hello",
    };

    await db.insert(messages).values(values);
    await expect(db.insert(messages).values(values)).resolves.toBeTruthy();
  });

  it("disappears with its business, leaving nothing orphaned", async () => {
    const businessId = await insertBusiness("Cascade Co", "osm/node/32");
    const leadRows = await db
      .insert(leads)
      .values({ businessId })
      .returning({ id: leads.id });
    const conversationRows = await db
      .insert(conversations)
      .values({ leadId: first(leadRows).id })
      .returning({ id: conversations.id });
    await db.insert(messages).values({
      conversationId: first(conversationRows).id,
      direction: "outbound",
      status: "sent",
      fromAddress: "jackhuhmate@gmail.com",
      toAddress: "owner@example.com",
      body: "hello",
    });

    await db.delete(businesses).where(eq(businesses.id, businessId));

    const remaining = await db
      .select({ id: messages.id })
      .from(messages)
      .where(eq(messages.conversationId, first(conversationRows).id));
    expect(remaining).toHaveLength(0);
  });
});

describe("workflow runs", () => {
  it("joins an existing run rather than starting a parallel one", async () => {
    await db
      .insert(workflowRuns)
      .values({ workflow: "outreach", idempotencyKey: "2026-07-31" });

    await expectRejectedBy(
      db
        .insert(workflowRuns)
        .values({ workflow: "outreach", idempotencyKey: "2026-07-31" }),
      "workflow_runs_idempotency_uq",
    );
  });

  it("records each step once per run, so a resumed run cannot repeat it", async () => {
    // The step that matters is "send the batch". Repeating it after a crash is not a retry.
    const runs = await db
      .insert(workflowRuns)
      .values({ workflow: "outreach", idempotencyKey: "2026-08-01" })
      .returning({ id: workflowRuns.id });
    const runId = first(runs).id;

    await db.insert(workflowSteps).values({ runId, name: "send_batch", sequence: 1 });

    await expectRejectedBy(
      db.insert(workflowSteps).values({ runId, name: "send_batch", sequence: 1 }),
      "workflow_steps_run_name_uq",
    );

    const otherRuns = await db
      .insert(workflowRuns)
      .values({ workflow: "outreach", idempotencyKey: "2026-08-02" })
      .returning({ id: workflowRuns.id });

    await expect(
      db
        .insert(workflowSteps)
        .values({ runId: first(otherRuns).id, name: "send_batch", sequence: 1 }),
    ).resolves.toBeTruthy();
  });
});

describe("events outbox", () => {
  it("refuses a duplicate dedupe key", async () => {
    await db.insert(events).values({
      type: "lead.contacted",
      aggregateType: "lead",
      dedupeKey: "lead.contacted:1",
    });

    await expectRejectedBy(
      db.insert(events).values({
        type: "lead.contacted",
        aggregateType: "lead",
        dedupeKey: "lead.contacted:1",
      }),
      "events_dedupe_key_uq",
    );
  });

  it("returns only unpublished events to the publisher", async () => {
    await db.insert(events).values([
      { type: "test.published", aggregateType: "test", publishedAt: new Date() },
      { type: "test.pending", aggregateType: "test" },
    ]);

    const pending = await db
      .select({ type: events.type })
      .from(events)
      .where(and(isNull(events.publishedAt), eq(events.aggregateType, "test")));

    expect(pending.map((row) => row.type)).toEqual(["test.pending"]);
  });
});

describe("pricing", () => {
  it("matches the fixed business model", () => {
    expect(BUILD_PRICE_PENCE).toBe(44_900);
    expect(CARE_PLAN_PENCE_PER_MONTH).toBe(3_900);
    expect(Number.isInteger(BUILD_PRICE_PENCE)).toBe(true);
  });

  it("defaults a care plan to £39/month in the database, not just in code", async () => {
    // The constant and the migration must agree, or a subscription created without an
    // explicit amount would bill the wrong figure.
    const businessId = await insertBusiness("Paying Co", "osm/node/40");
    const customerRows = await db
      .insert(customers)
      .values({ businessId })
      .returning({ id: customers.id });

    const rows = await db
      .insert(subscriptions)
      .values({ customerId: first(customerRows).id })
      .returning({
        amountPence: subscriptions.amountPence,
        currency: subscriptions.currency,
      });

    expect(first(rows).amountPence).toBe(CARE_PLAN_PENCE_PER_MONTH);
    expect(first(rows).currency).toBe("GBP");
  });
});
