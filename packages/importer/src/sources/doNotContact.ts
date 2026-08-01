import { normaliseEmail, suppressions } from "@agency/db";
import { and, eq } from "drizzle-orm";
import { parseCsvTable } from "../csv.js";
import type { ImportContext, SourceReport } from "../types.js";
import { ProblemLog, emptyStats } from "../types.js";

/**
 * `do_not_contact.csv` — the opt-out list.
 *
 * The most consequential file in the repository: a row missed here is an email to someone
 * who has asked not to be contacted, which is a PECR breach rather than a bug. The importer
 * therefore never drops a row silently — anything unparseable is reported, and an existing
 * suppression is left exactly as it is.
 *
 * The file is malformed: the header declares one column, `email`, while the rows carry two
 * (`address,reason`). That second cell is the evidence of the request and is preserved via
 * `extras` rather than discarded to fit the header.
 */
export async function importDoNotContact(
  ctx: ImportContext,
  text: string,
): Promise<SourceReport> {
  const table = parseCsvTable(text);
  const stats = emptyStats();
  const problems = new ProblemLog();
  const seen = new Set<string>();

  for (const record of table.records) {
    const raw = record.get("email") || (record.cells[0] ?? "");
    const address = normaliseEmail(raw);

    if (address === "" || !address.includes("@")) {
      stats.skipped += 1;
      problems.add(record.line, "no email address in the row");
      continue;
    }

    if (seen.has(address)) {
      stats.ignored += 1;
      continue;
    }
    seen.add(address);

    const note = record.extras.join(", ").trim();

    const existing = await ctx.db
      .select({ id: suppressions.id, note: suppressions.note })
      .from(suppressions)
      .where(
        and(eq(suppressions.kind, "email"), eq(suppressions.valueNormalised, address)),
      )
      .limit(1);

    const current = existing[0];
    if (current === undefined) {
      await ctx.db.insert(suppressions).values({
        kind: "email",
        valueNormalised: address,
        reason: "opt_out_request",
        note: note === "" ? null : note,
        source: "do_not_contact.csv",
      });
      stats.inserted += 1;
      continue;
    }

    // A suppression is never re-litigated: the reason and the date stand. Only the note is
    // backfilled, and only when we had none.
    if (current.note === null && note !== "") {
      await ctx.db
        .update(suppressions)
        .set({ note })
        .where(eq(suppressions.id, current.id));
      stats.updated += 1;
    } else {
      stats.unchanged += 1;
    }
  }

  return {
    source: "do_not_contact.csv",
    rows: table.records.length,
    stats,
    problems: problems.list(),
    problemCount: problems.count,
  };
}
