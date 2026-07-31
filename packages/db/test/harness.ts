import { fileURLToPath } from "node:url";
import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import type { PgliteDatabase } from "drizzle-orm/pglite";
import { migrate } from "drizzle-orm/pglite/migrator";
import * as schema from "../src/schema/index.js";

/**
 * A real Postgres for tests, in-process.
 *
 * PGlite is Postgres itself compiled to WASM, not an emulation, so enums, partial unique
 * indexes, `on delete cascade` and transactional behaviour all work exactly as they will in
 * production. That matters here more than usual: most of this schema's safety comes from
 * constraints, and a test double that ignores constraints would verify nothing.
 *
 * It also means CI needs no Docker service and no credentials, so the migration suite runs
 * on every push rather than only when someone remembers to start a container.
 */
export type TestDatabase = PgliteDatabase<typeof schema>;

export interface TestDatabaseHandle {
  readonly db: TestDatabase;
  close(): Promise<void>;
}

const MIGRATIONS_FOLDER = fileURLToPath(new URL("../drizzle", import.meta.url));

/** Apply every committed migration. Safe to call again: already-applied files are skipped. */
export async function applyMigrations(db: TestDatabase): Promise<void> {
  await migrate(db, { migrationsFolder: MIGRATIONS_FOLDER });
}

/**
 * Fresh database with all migrations applied.
 *
 * Migrations are applied rather than the schema being created directly, so every test run
 * is also a test that the committed migrations actually work from empty — the failure mode
 * where the code and the migrations have drifted apart is caught here rather than on the
 * VPS at deploy time.
 */
export async function createTestDatabase(): Promise<TestDatabaseHandle> {
  const client = new PGlite();
  const db = drizzle(client, { schema });
  await applyMigrations(db);
  return {
    db,
    close: () => client.close(),
  };
}
