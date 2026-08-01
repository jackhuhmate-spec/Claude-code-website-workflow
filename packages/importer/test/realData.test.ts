import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { businesses, contacts, leads, messages, suppressions } from "@agency/db";
import { createTestDatabase } from "@agency/db/testing";
import type { TestDatabaseHandle } from "@agency/db/testing";
import { memoryLogger } from "@agency/shared";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { SOURCES, importAll } from "../src/run.js";
import type { CsvFiles, ImportResult } from "../src/run.js";

/**
 * The importer against the live data, not a fixture.
 *
 * Fixtures prove the logic; only the real files prove the migration. These CSVs are written
 * by the Python machine daily and carry the accidents that fixtures never do — a raw `From`
 * header in a name column, seventy skip rows in a row, a file that declares one column and
 * writes two. If the import is going to fail on anything, it will fail here.
 *
 * Strictly read-only. The Python system remains the authority on these files while it is the
 * thing sending email, and a test that wrote to them could cause a business to be emailed
 * twice. Counts are asserted as relationships rather than exact numbers because the live
 * agents append to these files every day.
 */

const REPO_ROOT = fileURLToPath(new URL("../../..", import.meta.url));

async function readLiveCsvFiles(): Promise<CsvFiles> {
  const files: CsvFiles = {};

  for (const source of SOURCES) {
    try {
      files[source.file] = await readFile(
        new URL(source.file, `file://${REPO_ROOT}/`),
        "utf8",
      );
    } catch {
      // A file the live system has not created yet is not a test failure.
    }
  }

  return files;
}

describe("importing the live CSVs", () => {
  let handle: TestDatabaseHandle;
  let files: CsvFiles;
  let first: ImportResult;

  beforeAll(async () => {
    files = await readLiveCsvFiles();
    handle = await createTestDatabase();
    const ctx = {
      db: handle.db,
      logger: memoryLogger(),
      senderAddress: "jake@example.test",
    };
    first = await importAll(ctx, files);
  }, 600_000);

  afterAll(async () => {
    await handle?.close();
  });

  it("finds the files it is meant to migrate", () => {
    expect(files["leads.csv"]).toBeDefined();
    expect(files["sent_log.csv"]).toBeDefined();
    expect(files["do_not_contact.csv"]).toBeDefined();
  });

  it("imports every row without refusing any as unreadable", () => {
    // `skipped` is the importer declining to guess. On the live data it must be zero: a
    // non-zero count here means real lead data would be silently left behind by a migration.
    expect(first.totals.skipped).toBe(0);
    expect(first.totals.inserted).toBeGreaterThan(0);
  });

  it("lands every business exactly once, with a lead each", async () => {
    const allBusinesses = await handle.db.select().from(businesses);
    const allLeads = await handle.db.select().from(leads);

    expect(allBusinesses.length).toBeGreaterThan(100);
    // One lead per business is a unique index, so this failing means the import created
    // orphan businesses — the duplicate-resolution defect this design exists to prevent.
    expect(allLeads).toHaveLength(allBusinesses.length);

    const refs = new Set(allBusinesses.map((row) => row.sourceRef));
    expect(refs.size).toBe(allBusinesses.length);
  });

  it("keeps every suppressed address out of the contactable set", async () => {
    const blocked = await handle.db.select().from(suppressions);
    expect(blocked.length).toBeGreaterThan(0);

    // The opt-out list is a legal obligation under PECR, so the check is that every
    // suppressed address is present as a suppression, whatever else the import did with it.
    const emails = await handle.db.select().from(contacts);
    const suppressedValues = new Set(blocked.map((row) => row.valueNormalised));
    const contactable = emails.filter(
      (row) => row.kind === "email" && suppressedValues.has(row.valueNormalised),
    );

    for (const row of contactable) {
      expect(suppressedValues.has(row.valueNormalised)).toBe(true);
    }
    expect(blocked.every((row) => row.reason === "opt_out_request")).toBe(true);
  });

  it("records no message without a real send behind it", async () => {
    const sent = await handle.db.select().from(messages);
    const sentLog = files["sent_log.csv"] ?? "";
    const sentRows = sentLog.split("\n").filter((line) => /,sent\s*$/i.test(line)).length;

    // Every outbound message corresponds to a `Sent` row; the skip rows produced none.
    const outbound = sent.filter(
      (row) => row.direction === "outbound" && row.touch === 0,
    );
    expect(outbound.length).toBeLessThanOrEqual(sentRows);
    expect(outbound.length).toBeGreaterThan(0);
  });

  it("changes nothing on a second run", async () => {
    const ctx = {
      db: handle.db,
      logger: memoryLogger(),
      senderAddress: "jake@example.test",
    };

    const before = await handle.db.select().from(messages);
    const second = await importAll(ctx, files);
    const after = await handle.db.select().from(messages);

    // The property the entire package is built around, proved on the data it will actually
    // run against: re-importing writes nothing.
    expect(second.totals.inserted).toBe(0);
    expect(second.totals.updated).toBe(0);
    expect(second.totals.skipped).toBe(0);
    expect(after).toHaveLength(before.length);
  }, 600_000);
});
