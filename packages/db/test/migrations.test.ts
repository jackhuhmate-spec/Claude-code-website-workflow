import { sql } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { applyMigrations, createTestDatabase } from "../src/testing/harness.js";
import type { TestDatabaseHandle } from "../src/testing/harness.js";

/**
 * The committed migrations are the only thing that will ever touch production, so they —
 * not the TypeScript schema — are what these tests exercise. `createTestDatabase` applies
 * them to an empty database, which means any drift between `src/schema` and `drizzle/`
 * fails here rather than at deploy time.
 */
describe("migrations", () => {
  let handle: TestDatabaseHandle;

  beforeAll(async () => {
    handle = await createTestDatabase();
  });

  afterAll(async () => {
    await handle.close();
  });

  async function publicTables(): Promise<string[]> {
    const result = await handle.db.execute(
      sql`select table_name from information_schema.tables where table_schema = 'public' order by table_name`,
    );
    return result.rows.map((row) => String(row["table_name"]));
  }

  it("creates every table the platform depends on", async () => {
    const tables = await publicTables();

    expect(tables).toEqual([
      "agent_runs",
      "audit_log",
      "businesses",
      "contacts",
      "conversations",
      "customers",
      "deployments",
      "events",
      "lead_scores",
      "leads",
      "messages",
      "payments",
      "projects",
      "revisions",
      "site_audits",
      "subscriptions",
      "suppressions",
      "tasks",
      "websites",
      "workflow_runs",
      "workflow_steps",
    ]);
  });

  it("stores every timestamp with a time zone", async () => {
    // London is UTC+1 for half the year. A naive `timestamp` makes "was this sent today?"
    // ambiguous twice a year, which is precisely the question the daily cap turns on.
    const result = await handle.db.execute(
      sql`select table_name, column_name, data_type
          from information_schema.columns
          where table_schema = 'public' and data_type like 'timestamp%'
            and data_type <> 'timestamp with time zone'`,
    );

    expect(result.rows).toEqual([]);
  });

  it("stores money as integers so pence never drift", async () => {
    const result = await handle.db.execute(
      sql`select data_type from information_schema.columns
          where table_schema = 'public' and column_name like '%pence%'`,
    );

    expect(result.rows.length).toBeGreaterThan(0);
    for (const row of result.rows) {
      expect(row["data_type"]).toBe("integer");
    }
  });

  it("is idempotent — re-running the migrator changes nothing", async () => {
    // Deploys re-run the migrator every time. If a second pass were not a no-op, a redeploy
    // would attempt to recreate live tables.
    const before = await publicTables();
    await applyMigrations(handle.db);

    expect(await publicTables()).toEqual(before);
  });
});
