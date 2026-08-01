import { ValidationError } from "@agency/shared";

/**
 * A minimal RFC 4180 reader.
 *
 * Written rather than taken as a dependency because the requirement is small, fixed and
 * fully testable: these files are produced by Python's `csv` module and read once. What it
 * must get right is the quoting — `Biggest Flaw` is free prose containing commas, quotes
 * and occasionally newlines, and a `split(",")` would shred it into columns that then
 * silently land in the wrong fields.
 *
 * It is deliberately tolerant of ragged rows: `do_not_contact.csv` has a one-column header
 * and two-column data, and dropping the second column would discard the opt-out evidence.
 */

export interface CsvRecord {
  /** 1-based line the record starts on, for error messages that point at the file. */
  readonly line: number;
  readonly cells: readonly string[];
  /** Value for a header, or `""` when the row is short. Never throws. */
  get(header: string): string;
  /** Cells beyond the header row. Empty for well-formed files. */
  readonly extras: readonly string[];
}

export interface CsvTable {
  readonly headers: readonly string[];
  readonly records: readonly CsvRecord[];
}

/** A row before headers are applied. `line` is the 1-based line the row started on. */
export interface RawRecord {
  readonly line: number;
  readonly cells: string[];
}

/** Split CSV text into raw rows. Blank lines are skipped; quoted content is preserved. */
export function parseCsv(text: string): RawRecord[] {
  const source = text.startsWith("﻿") ? text.slice(1) : text;
  const records: RawRecord[] = [];

  let cells: string[] = [];
  let field = "";
  let inQuotes = false;
  let started = false;
  let line = 1;
  let recordLine = 1;

  const endField = (): void => {
    cells.push(field);
    field = "";
  };

  const endRecord = (): void => {
    // A trailing newline would otherwise produce a phantom row of one empty cell.
    if (started) {
      endField();
      records.push({ line: recordLine, cells });
    }
    cells = [];
    field = "";
    started = false;
    recordLine = line;
  };

  for (let i = 0; i < source.length; i += 1) {
    const ch = source.charAt(i);

    if (inQuotes) {
      if (ch === '"') {
        if (source.charAt(i + 1) === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        if (ch === "\n") {
          line += 1;
        }
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
      started = true;
    } else if (ch === ",") {
      started = true;
      endField();
    } else if (ch === "\n") {
      line += 1;
      endRecord();
    } else if (ch === "\r") {
      // Swallow CRLF; a lone CR is treated as the line ending it almost certainly is.
      if (source.charAt(i + 1) === "\n") {
        continue;
      }
      line += 1;
      endRecord();
    } else {
      started = true;
      field += ch;
    }
  }

  if (inQuotes) {
    throw new ValidationError(
      "csv.unterminated_quote",
      "CSV ends inside a quoted field",
      {
        context: { line: recordLine },
      },
    );
  }
  endRecord();

  return records;
}

/**
 * Parse into header-addressed records.
 *
 * Headers are matched case-insensitively and with surrounding whitespace ignored, because
 * the six source files were written at different times and disagree about both — `leads.csv`
 * uses `Business Name` where `replies_log.csv` uses `business`.
 */
export function parseCsvTable(text: string): CsvTable {
  const raw = parseCsv(text);
  const headerRow = raw[0];
  if (headerRow === undefined) {
    return { headers: [], records: [] };
  }

  const headers = headerRow.cells.map((cell) => cell.trim());
  const indexByHeader = new Map<string, number>();
  headers.forEach((header, index) => {
    const key = header.toLowerCase();
    // First wins: a duplicated column name is a file defect, not a reason to reshuffle.
    if (!indexByHeader.has(key)) {
      indexByHeader.set(key, index);
    }
  });

  const records = raw.slice(1).map((row): CsvRecord => {
    const cells = row.cells;
    return {
      line: row.line,
      cells,
      extras: cells.slice(headers.length),
      get(header: string): string {
        const index = indexByHeader.get(header.trim().toLowerCase());
        if (index === undefined) {
          return "";
        }
        return cells[index]?.trim() ?? "";
      },
    };
  });

  return { headers, records };
}
