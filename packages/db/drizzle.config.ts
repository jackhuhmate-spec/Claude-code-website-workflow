import { defineConfig } from "drizzle-kit";

/**
 * Migrations are generated files, committed to the repository and applied in order.
 *
 * `drizzle-kit push` is deliberately not used anywhere: it diffs the schema against a live
 * database and applies the result, which is convenient in development and unacceptable
 * against production data, where the difference between "add a column" and "drop and
 * recreate a table" is the entire lead list.
 */
export default defineConfig({
  dialect: "postgresql",
  schema: "./src/schema/index.ts",
  out: "./drizzle",
  strict: true,
  verbose: true,
  dbCredentials: {
    url: process.env["DATABASE_URL"] ?? "postgres://localhost:5432/agency",
  },
});
