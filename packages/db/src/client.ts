import type { Logger as AppLogger } from "@agency/shared";
import { ConfigError, UpstreamError } from "@agency/shared";
import type { ExtractTablesWithRelations } from "drizzle-orm";
import { drizzle } from "drizzle-orm/node-postgres";
import type { NodePgDatabase } from "drizzle-orm/node-postgres";
import type { PgDatabase, PgQueryResultHKT } from "drizzle-orm/pg-core";
import pg from "pg";
import * as schema from "./schema/index.js";

/**
 * The database as callers see it: driver-agnostic.
 *
 * Widened from `NodePgDatabase` deliberately. Every repository and importer is typed
 * against this, so the same code runs against `pg` in production and against PGlite in
 * tests — if it named the driver, the only way to test a query would be a live Postgres.
 */
export type Database = PgDatabase<
  PgQueryResultHKT,
  typeof schema,
  ExtractTablesWithRelations<typeof schema>
>;

export interface DatabaseHandle {
  readonly db: Database;
  /** Releases the pool. Always call it on shutdown or the process will not exit. */
  close(): Promise<void>;
}

export interface DatabaseOptions {
  readonly connectionString: string;
  /**
   * Pool ceiling. Kept low by default: this runs on a single small VPS beside Postgres
   * itself, and an oversized pool starves the database rather than speeding anything up.
   */
  readonly maxConnections?: number;
  readonly logger?: AppLogger;
  /** Managed Postgres providers generally require TLS; a local socket does not. */
  readonly ssl?: boolean;
}

export interface NodePgDatabaseHandle {
  readonly db: NodePgDatabase<typeof schema>;
  close(): Promise<void>;
}

/**
 * Build the pooled database handle, keeping the concrete driver type.
 *
 * Only the migration runner needs this: drizzle's node-postgres migrator is tied to its own
 * driver and will not accept the widened `Database`. Everything else should take
 * `createDatabase`, so it stays testable.
 *
 * Connection details arrive as a parameter rather than being read from `process.env` here,
 * so composition stays in one place and tests never depend on ambient environment.
 */
export function createNodePgDatabase(options: DatabaseOptions): NodePgDatabaseHandle {
  if (options.connectionString.trim() === "") {
    throw new ConfigError("db.missing_connection_string", "DATABASE_URL is empty");
  }

  const pool = new pg.Pool({
    connectionString: options.connectionString,
    max: options.maxConnections ?? 10,
    // A connection that cannot be established in 10s will not be established; failing
    // fast surfaces the real problem instead of stalling a send window.
    connectionTimeoutMillis: 10_000,
    idleTimeoutMillis: 30_000,
    ...(options.ssl === true ? { ssl: { rejectUnauthorized: true } } : {}),
  });

  // An idle client that errors takes the pool's slot with it. Unhandled, it also crashes
  // the process, which for a worker mid-cycle means losing whatever it was doing.
  pool.on("error", (error: Error) => {
    options.logger?.error(
      { err: new UpstreamError("db.idle_client_error", error.message, { cause: error }) },
      "idle postgres client errored",
    );
  });

  return {
    db: drizzle(pool, { schema }),
    close: () => pool.end(),
  };
}

/** The handle the application uses. Driver-agnostic, so call sites stay testable. */
export function createDatabase(options: DatabaseOptions): DatabaseHandle {
  return createNodePgDatabase(options);
}

export { schema };
