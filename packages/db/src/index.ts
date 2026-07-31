export { createDatabase, schema } from "./client.js";
export type { Database, DatabaseHandle, DatabaseOptions } from "./client.js";

export { MIGRATIONS_FOLDER, runMigrations } from "./migrate.js";

// Tables, enums and the pricing constants are re-exported flat so callers write
// `import { leads, BUILD_PRICE_PENCE } from "@agency/db"` rather than reaching into paths.
export * from "./schema/index.js";
