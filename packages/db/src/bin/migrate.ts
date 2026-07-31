#!/usr/bin/env node
import { createLogger, isAppError, requireSecret } from "@agency/shared";
import { runMigrations } from "../migrate.js";

/**
 * Production migration entry point: `pnpm --filter @agency/db migrate`.
 *
 * Deliberately a separate process from the application. Migrations run once, on deploy,
 * with a single connection; letting a worker apply them on boot means every replica races
 * to alter the same tables.
 */
async function main(): Promise<void> {
  const logger = createLogger({ service: "db-migrate" });
  const connectionString = requireSecret("DATABASE_URL", process.env);

  await runMigrations({
    connectionString,
    // One connection is enough for a one-shot task and keeps the pool from lingering.
    maxConnections: 1,
    ssl: process.env["DATABASE_SSL"] === "true",
    logger,
  });
}

main().catch((error: unknown) => {
  // Written to stderr rather than the logger: if config loading itself failed there may be
  // no logger, and a migration failure must be visible in raw deploy output regardless.
  const detail = isAppError(error) ? `${error.code}: ${error.message}` : String(error);
  process.stderr.write(`migration failed — ${detail}\n`);
  process.exitCode = 1;
});
