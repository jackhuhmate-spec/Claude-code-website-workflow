import { fileURLToPath } from "node:url";
import { PGlite } from "@electric-sql/pglite";
import { drizzle } from "drizzle-orm/pglite";
import type { PgliteDatabase } from "drizzle-orm/pglite";
import { migrate } from "drizzle-orm/pglite/migrator";
import type { Database } from "../client.js";
import * as schema from "../schema/index.js";

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
 *
 * Published as `@agency/db/testing` rather than kept in this package's `test/` folder,
 * because every package above it needs the same database to test against and reaching into
 * another package's test directory breaks the moment either one is restructured.
 * `@electric-sql/pglite` stays a devDependency: only test code ever imports this module.
 */
export type TestDatabase = PgliteDatabase<typeof schema>;

/**
 * Compile-time proof that the PGlite handle satisfies the driver-agnostic `Database` the
 * application is written against. If this ever stops holding, every integration test is
 * testing something the production code could not accept.
 */
export type TestDatabaseIsADatabase = TestDatabase extends Database ? true : never;

export interface TestDatabaseHandle {
  readonly db: TestDatabase;
  close(): Promise<void>;
}

/**
 * Resolved from this module rather than the working directory, so the harness works the same
 * whether it is loaded from `src` by vitest or from `dist` by a consuming package.
 */
export const TEST_MIGRATIONS_FOLDER = fileURLToPath(
  new URL("../../drizzle", import.meta.url),
);

/** Apply every committed migration. Safe to call again: already-applied files are skipped. */
export async function applyMigrations(db: TestDatabase): Promise<void> {
  await migrate(db, { migrationsFolder: TEST_MIGRATIONS_FOLDER });
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

// Instantiate the proof so the compiler actually checks it.
const _assertDatabaseCompatible: TestDatabaseIsADatabase = true;
void _assertDatabaseCompatible;
