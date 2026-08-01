import { fileURLToPath } from "node:url";
import { UpstreamError } from "@agency/shared";
import { migrate as drizzleMigrate } from "drizzle-orm/node-postgres/migrator";
import { createNodePgDatabase } from "./client.js";
import type { DatabaseOptions } from "./client.js";

/**
 * Resolved from this module rather than the working directory, so migrations apply
 * identically whether run from the repo root, from `packages/db`, or from a container
 * whose CWD is `/app`.
 */
export const MIGRATIONS_FOLDER = fileURLToPath(new URL("../drizzle", import.meta.url));

/**
 * Apply every pending migration, in order, then release the connection.
 *
 * Drizzle records applied migrations in `drizzle.__drizzle_migrations` and each file runs
 * inside a transaction, so a failure part-way leaves the database on the last complete
 * migration rather than in a half-applied state. Re-running after a fix is safe.
 */
export async function runMigrations(options: DatabaseOptions): Promise<void> {
  const handle = createNodePgDatabase(options);
  try {
    options.logger?.info({ folder: MIGRATIONS_FOLDER }, "applying migrations");
    await drizzleMigrate(handle.db, { migrationsFolder: MIGRATIONS_FOLDER });
    options.logger?.info({ folder: MIGRATIONS_FOLDER }, "migrations up to date");
  } catch (error) {
    throw new UpstreamError(
      "db.migration_failed",
      error instanceof Error ? error.message : "migration failed",
      { cause: error, context: { folder: MIGRATIONS_FOLDER } },
    );
  } finally {
    await handle.close();
  }
}
