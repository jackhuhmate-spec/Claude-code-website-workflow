import {
  BUILD_PRICE_PENCE,
  CARE_PLAN_PENCE_PER_MONTH,
  customers,
  leads,
  payments,
  subscriptions,
} from "@agency/db";
import { eq } from "drizzle-orm";
import { parseCsvTable } from "../csv.js";
import { changedFields, hasChanges } from "../diff.js";
import { findOrCreateBusiness, findOrCreateLead, parseCsvDate } from "../entities.js";
import type { ImportContext, SourceReport } from "../types.js";
import { ProblemLog, emptyStats } from "../types.js";

/**
 * `payments.csv` — money in. Currently header-only, which is the point of importing it now:
 * the first sale must land in Postgres rather than prompt someone to invent a schema for it
 * under time pressure.
 *
 * Columns: `date,business,amount_gbp,type,status,notes`.
 */
export function paymentReference(
  business: string,
  date: string,
  amountPence: number,
): string {
  return `csv:payment:${business}:${date}:${String(amountPence)}`;
}

type PaymentKind =
  "build_deposit" | "build_balance" | "build_full" | "subscription" | "refund";

type PaymentStatus = "due" | "paid" | "failed" | "refunded" | "written_off";

const KIND_BY_TYPE = new Map<string, PaymentKind>([
  ["deposit", "build_deposit"],
  ["build_deposit", "build_deposit"],
  ["balance", "build_balance"],
  ["build_balance", "build_balance"],
  ["build", "build_full"],
  ["full", "build_full"],
  ["build_full", "build_full"],
  ["care", "subscription"],
  ["care_plan", "subscription"],
  ["subscription", "subscription"],
  ["monthly", "subscription"],
  ["refund", "refund"],
]);

/**
 * Every status `ops/record_payment.py` can write, plus the obvious synonyms.
 *
 * That script is the only producer of this file, and its vocabulary is
 * `paid | deposit | quoted | overdue | refunded`. Anything it emits must map to something
 * true here: an unmapped status silently falling back to `due` would record money that has
 * already been received as outstanding.
 *
 * `deposit` is the awkward one. It is written in the status column but describes the *kind*
 * of payment — a 50% deposit that has in fact been taken — so it means paid, and the kind is
 * narrowed alongside it in `resolveKind`. `quoted` and `overdue` are both genuinely unpaid
 * and the schema distinguishes them by `dueAt`, not by a separate state.
 */
const STATUS_BY_TEXT = new Map<string, PaymentStatus>([
  ["paid", "paid"],
  ["received", "paid"],
  ["deposit", "paid"],
  ["due", "due"],
  ["quoted", "due"],
  ["overdue", "due"],
  ["pending", "due"],
  ["outstanding", "due"],
  ["failed", "failed"],
  ["refunded", "refunded"],
  ["written_off", "written_off"],
  ["write_off", "written_off"],
]);

/**
 * A deposit recorded as `--type build --status deposit` is a part payment, not the full
 * £449. Filing it as `build_full` would report the build as settled and stop the balance
 * ever being chased.
 */
function resolveKind(kind: PaymentKind, statusText: string): PaymentKind {
  if (statusText === "deposit" && (kind === "build_full" || kind === "build_balance")) {
    return "build_deposit";
  }
  return kind;
}

/**
 * Pounds to pence, without floating point.
 *
 * `449.50 * 100` is `44949.999…` in binary floating point, and a rounding error in a money
 * column is the kind of defect that is only ever found by a customer. Parsing the decimal
 * text directly avoids the question entirely.
 */
export function parseGbpToPence(value: string): number | null {
  const trimmed = value.trim().replace(/^£/, "").replace(/,/g, "");
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(trimmed);
  if (match === null) {
    return null;
  }
  const [, sign, whole, fraction = ""] = match;
  if (whole === undefined) {
    return null;
  }
  const pence = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return sign === "-" ? -pence : pence;
}

export async function importPayments(
  ctx: ImportContext,
  text: string,
): Promise<SourceReport> {
  const table = parseCsvTable(text);
  const stats = emptyStats();
  const problems = new ProblemLog();

  for (const record of table.records) {
    const name = record.get("business").trim();
    const dateText = record.get("date").trim();
    const paidAt = parseCsvDate(dateText);
    const amountPence = parseGbpToPence(record.get("amount_gbp"));

    if (name === "" || paidAt === null || amountPence === null) {
      stats.skipped += 1;
      problems.add(record.line, "a payment row is missing its business, date or amount");
      continue;
    }

    const declaredKind = KIND_BY_TYPE.get(record.get("type").trim().toLowerCase());
    if (declaredKind === undefined) {
      // Money is never guessed at. An unrecognised type is escalated as a defect rather
      // than filed under a plausible-looking kind that would then be reported as revenue.
      stats.skipped += 1;
      problems.add(record.line, `unrecognised payment type "${record.get("type")}"`);
      continue;
    }

    const statusText = record.get("status").trim().toLowerCase();
    const status = STATUS_BY_TEXT.get(statusText);
    if (status === undefined) {
      // Same rule as the type column: a status nobody has taught this importer about could
      // mean paid or unpaid, and the difference is the whole point of the file.
      stats.skipped += 1;
      problems.add(record.line, `unrecognised payment status "${record.get("status")}"`);
      continue;
    }

    const kind = resolveKind(declaredKind, statusText);
    const reference = paymentReference(name, dateText, amountPence);

    const existing = await ctx.db
      .select({ id: payments.id, status: payments.status })
      .from(payments)
      .where(eq(payments.reference, reference))
      .limit(1);

    const current = existing[0];
    if (current !== undefined) {
      // The only field a re-import may move is status: a row can go from due to paid.
      const changes = changedFields(current, { status });
      if (hasChanges(changes)) {
        await ctx.db
          .update(payments)
          .set({ ...changes, updatedAt: new Date() })
          .where(eq(payments.id, current.id));
        stats.updated += 1;
      } else {
        stats.unchanged += 1;
      }
      continue;
    }

    const customerId = await findOrCreateCustomer(ctx, name, paidAt);
    const subscriptionId =
      kind === "subscription"
        ? await findOrCreateSubscription(ctx, customerId, paidAt)
        : null;

    await ctx.db.insert(payments).values({
      customerId,
      subscriptionId,
      kind,
      status,
      amountPence,
      method: "cash",
      reference,
      note: record.get("notes").trim() || null,
      paidAt: status === "paid" ? paidAt : null,
      dueAt: status === "paid" ? null : paidAt,
    });
    stats.inserted += 1;

    if (amountPence > 0 && kind !== "subscription" && amountPence < BUILD_PRICE_PENCE) {
      // Not a defect — a deposit is meant to be short of the full price — but a *build_full*
      // below £449 would breach the no-discount rule, so the amount is surfaced either way.
      problems.add(
        record.line,
        `${kind} of £${(amountPence / 100).toFixed(2)} is below £449`,
      );
    }
  }

  return {
    source: "payments.csv",
    rows: table.records.length,
    stats,
    problems: problems.list(),
    problemCount: problems.count,
  };
}

/**
 * A payment implies a customer, which implies a won lead.
 *
 * The CSV records only the business name, so the rest of the chain is created rather than
 * demanded — refusing to import a real payment because no lead row exists would lose the
 * one fact in this repository that is unambiguously true: someone paid.
 */
async function findOrCreateCustomer(
  ctx: ImportContext,
  name: string,
  wonAt: Date,
): Promise<string> {
  const businessId = await findOrCreateBusiness(ctx, { name, area: null });
  const leadId = await findOrCreateLead(ctx, businessId);

  const existing = await ctx.db
    .select({ id: customers.id })
    .from(customers)
    .where(eq(customers.businessId, businessId))
    .limit(1);

  const current = existing[0];
  if (current !== undefined) {
    return current.id;
  }

  await ctx.db
    .update(leads)
    .set({ status: "won", updatedAt: new Date() })
    .where(eq(leads.id, leadId));

  const inserted = await ctx.db
    .insert(customers)
    .values({ businessId, leadId, wonAt })
    .returning({ id: customers.id });

  const row = inserted[0];
  if (row === undefined) {
    throw new Error("customer insert returned no row");
  }
  return row.id;
}

/** The £39/month care plan, priced from the constant so no path can invent a figure. */
async function findOrCreateSubscription(
  ctx: ImportContext,
  customerId: string,
  startedAt: Date,
): Promise<string> {
  const existing = await ctx.db
    .select({ id: subscriptions.id })
    .from(subscriptions)
    .where(eq(subscriptions.customerId, customerId))
    .limit(1);

  const current = existing[0];
  if (current !== undefined) {
    return current.id;
  }

  const inserted = await ctx.db
    .insert(subscriptions)
    .values({ customerId, amountPence: CARE_PLAN_PENCE_PER_MONTH, startedAt })
    .returning({ id: subscriptions.id });

  const row = inserted[0];
  if (row === undefined) {
    throw new Error("subscription insert returned no row");
  }
  return row.id;
}
