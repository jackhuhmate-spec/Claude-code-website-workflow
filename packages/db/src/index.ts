export { createDatabase, createNodePgDatabase, schema } from "./client.js";
export type {
  Database,
  DatabaseHandle,
  DatabaseOptions,
  NodePgDatabaseHandle,
} from "./client.js";

export { MIGRATIONS_FOLDER, runMigrations } from "./migrate.js";

export {
  normaliseEmail,
  normaliseHost,
  normaliseName,
  normalisePhone,
} from "./normalise.js";

// Tables, enums and the pricing constants are re-exported flat so callers write
// `import { leads, BUILD_PRICE_PENCE } from "@agency/db"` rather than reaching into paths.
export * from "./schema/index.js";
