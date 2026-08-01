import type { ImportContext, SourceReport } from "./types.js";
import { importDoNotContact } from "./sources/doNotContact.js";
import { importFollowUpsLog } from "./sources/followupsLog.js";
import { importLeads } from "./sources/leads.js";
import { importPayments } from "./sources/payments.js";
import { importRepliesLog } from "./sources/repliesLog.js";
import { importSentLog } from "./sources/sentLog.js";

/**
 * The CSV files the Python machine maintains, keyed by filename.
 *
 * A missing file is not an error. `payments.csv` is header-only today and the logs did not
 * all exist from the beginning, so an import that refused to run without the full set would
 * be unusable on exactly the repositories it is meant to migrate.
 */
export type CsvFileName =
  | "leads.csv"
  | "do_not_contact.csv"
  | "sent_log.csv"
  | "followups_log.csv"
  | "replies_log.csv"
  | "payments.csv";

export type CsvFiles = Partial<Record<CsvFileName, string>>;

interface SourceDefinition {
  readonly file: CsvFileName;
  readonly run: (ctx: ImportContext, text: string) => Promise<SourceReport>;
}

/**
 * Order is a correctness requirement, not a preference.
 *
 * `leads.csv` first, because it is the only file carrying an area and so the only one that
 * can establish a business under its full key; every later file resolves by email against
 * the contacts it created. `do_not_contact.csv` second, so a suppression is in place before
 * any history is attached to that address. The logs then run oldest concern to newest:
 * sends, chases, replies. Payments last, because a payment can promote a lead to `won` and
 * nothing afterwards should move it back.
 */
export const SOURCES: readonly SourceDefinition[] = [
  { file: "leads.csv", run: importLeads },
  { file: "do_not_contact.csv", run: importDoNotContact },
  { file: "sent_log.csv", run: importSentLog },
  { file: "followups_log.csv", run: importFollowUpsLog },
  { file: "replies_log.csv", run: importRepliesLog },
  { file: "payments.csv", run: importPayments },
];

export interface ImportResult {
  readonly reports: readonly SourceReport[];
  readonly missing: readonly CsvFileName[];
  readonly totals: {
    readonly inserted: number;
    readonly updated: number;
    readonly unchanged: number;
    readonly skipped: number;
    readonly ignored: number;
    readonly problems: number;
  };
}

/**
 * Run every source in dependency order.
 *
 * Sources run sequentially and share one context: they write to the same businesses and
 * leads, so concurrency here would race two sources into creating the same row and turn a
 * unique index into an intermittent crash.
 */
export async function importAll(
  ctx: ImportContext,
  files: CsvFiles,
): Promise<ImportResult> {
  const reports: SourceReport[] = [];
  const missing: CsvFileName[] = [];

  for (const source of SOURCES) {
    const text = files[source.file];
    if (text === undefined) {
      missing.push(source.file);
      ctx.logger.warn({ file: source.file }, "csv not supplied; source skipped");
      continue;
    }

    const report = await source.run(ctx, text);
    reports.push(report);
    ctx.logger.info(
      {
        file: source.file,
        rows: report.rows,
        ...report.stats,
        problems: report.problemCount,
      },
      "source imported",
    );

    for (const problem of report.problems) {
      ctx.logger.warn({ file: source.file, problem }, "row not imported as written");
    }
  }

  return { reports, missing, totals: total(reports) };
}

function total(reports: readonly SourceReport[]): ImportResult["totals"] {
  return reports.reduce(
    (acc, report) => ({
      inserted: acc.inserted + report.stats.inserted,
      updated: acc.updated + report.stats.updated,
      unchanged: acc.unchanged + report.stats.unchanged,
      skipped: acc.skipped + report.stats.skipped,
      ignored: acc.ignored + report.stats.ignored,
      problems: acc.problems + report.problemCount,
    }),
    { inserted: 0, updated: 0, unchanged: 0, skipped: 0, ignored: 0, problems: 0 },
  );
}
