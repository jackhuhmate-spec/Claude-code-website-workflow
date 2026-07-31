import type { Logger as AppLogger } from "@agency/shared";
import { ConfigError, UpstreamError } from "@agency/shared";
import { drizzle } from "drizzle-orm/node-postgres";
import type { NodePgDatabase } from "drizzle-orm/node-postgres";
import pg from "pg";
import * as schema from "./schema/index.js";

export type Database = NodePgDatabase<typeof schema>;

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

/**
 * Build the pooled database handle.
 *
 * Connection details arrive as a parameter rather than being read from `process.env` here,
 * so composition stays in one place and tests never depend on ambient environment.
 */
export function createDatabase(options: DatabaseOptions): DatabaseHandle {
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

export { schema };
