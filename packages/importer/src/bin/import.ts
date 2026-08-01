#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createDatabase } from "@agency/db";
import { createLogger, isAppError, requireSecret } from "@agency/shared";
import { SOURCES, importAll } from "../run.js";
import type { CsvFiles } from "../run.js";

/**
 * One-shot CSV → Postgres import: `pnpm --filter @agency/importer import [dir]`.
 *
 * Read-only with respect to the CSVs. The Python machine remains the authority on those
 * files for as long as it is the thing sending email; this process must never write to them,
 * because a half-finished import that had rewritten `sent_log.csv` could cause a business to
 * be emailed twice.
 *
 * Safe to run repeatedly — that is the property the whole package is built around.
 */
async function main(): Promise<void> {
  const logger = createLogger({ service: "importer" });
  const directory = resolve(process.argv[2] ?? process.cwd());
  const connectionString = requireSecret("DATABASE_URL", process.env);

  // The account the historic mail was sent from. Read from config, never written as a
  // literal: the sending identity is deployment configuration.
  const senderAddress = requireSecret("GMAIL_USER", process.env);

  const files = await readCsvFiles(directory);
  const handle = createDatabase({ connectionString, maxConnections: 1 });

  try {
    const result = await importAll({ db: handle.db, logger, senderAddress }, files);
    logger.info(
      { directory, ...result.totals, missing: result.missing },
      "import complete",
    );

    for (const report of result.reports) {
      process.stdout.write(
        `${report.source.padEnd(20)} rows=${String(report.rows).padStart(4)} ` +
          `inserted=${String(report.stats.inserted)} updated=${String(report.stats.updated)} ` +
          `unchanged=${String(report.stats.unchanged)} skipped=${String(report.stats.skipped)} ` +
          `ignored=${String(report.stats.ignored)} problems=${String(report.problemCount)}\n`,
      );
    }

    // Skipped rows are data the importer refused to guess at, so they are reported as a
    // non-zero exit: a silent partial import is how a lead quietly disappears.
    if (result.totals.skipped > 0) {
      process.exitCode = 1;
    }
  } finally {
    await handle.close();
  }
}

async function readCsvFiles(directory: string): Promise<CsvFiles> {
  const files: CsvFiles = {};

  for (const source of SOURCES) {
    const text = await readIfPresent(resolve(directory, source.file));
    if (text !== null) {
      files[source.file] = text;
    }
  }

  return files;
}

/** A missing CSV is reported by `importAll`, not treated as a crash. */
async function readIfPresent(path: string): Promise<string | null> {
  try {
    return await readFile(path, "utf8");
  } catch (error: unknown) {
    if (isNodeError(error) && error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function isNodeError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error;
}

void main().catch((error: unknown) => {
  const detail = isAppError(error) ? `${error.code}: ${error.message}` : String(error);
  process.stderr.write(`import failed — ${detail}\n`);
  process.exitCode = 1;
});
