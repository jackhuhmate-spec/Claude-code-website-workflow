import type { Database } from "@agency/db";
import type { Logger } from "@agency/shared";

export interface ImportStats {
  inserted: number;
  updated: number;
  unchanged: number;
  /** Rows the importer refused to guess at. Always explained in `problems`. */
  skipped: number;
  /**
   * Rows that are correctly not records: `sent_log.csv` logs "Skipped - No Email Found"
   * as faithfully as it logs a send. Kept apart from `skipped` so a genuine data defect
   * stays visible instead of being buried under 300 routine non-sends.
   */
  ignored: number;
}

export interface SourceReport {
  readonly source: string;
  readonly rows: number;
  readonly stats: ImportStats;
  /**
   * Why rows were skipped, capped so a systematically malformed file cannot exhaust
   * memory. `problemCount` is the true total.
   */
  readonly problems: readonly string[];
  readonly problemCount: number;
}

export interface ImportContext {
  readonly db: Database;
  readonly logger: Logger;
  /**
   * The account the historic emails were sent from. Supplied by the caller from
   * configuration rather than written here — the sending identity is deployment config,
   * and a literal in the import code would be wrong the moment it changes.
   */
  readonly senderAddress: string;
}

export function emptyStats(): ImportStats {
  return { inserted: 0, updated: 0, unchanged: 0, skipped: 0, ignored: 0 };
}

const MAX_REPORTED_PROBLEMS = 20;

/** Collects skip reasons without letting a broken file grow without bound. */
export class ProblemLog {
  private readonly entries: string[] = [];
  private total = 0;

  add(line: number, reason: string): void {
    this.total += 1;
    if (this.entries.length < MAX_REPORTED_PROBLEMS) {
      this.entries.push(`line ${String(line)}: ${reason}`);
    }
  }

  get count(): number {
    return this.total;
  }

  list(): readonly string[] {
    return this.entries;
  }
}
