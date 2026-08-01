import { createTestDatabase } from "@agency/db/testing";
import type { TestDatabase, TestDatabaseHandle } from "@agency/db/testing";
import {
  businesses,
  contacts,
  conversations,
  customers,
  events,
  leads,
  messages,
  payments,
  siteAudits,
  subscriptions,
  suppressions,
} from "@agency/db";
import { memoryLogger } from "@agency/shared";
import { isNull } from "drizzle-orm";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { importAll } from "../src/run.js";
import type { CsvFiles } from "../src/run.js";
import { parseGbpToPence } from "../src/sources/payments.js";
import type { ImportContext } from "../src/types.js";

/**
 * The importer's contract, stated as tests: it fans one CSV row out into the tables that
 * replace it, it resolves the log files onto the businesses `leads.csv` created rather than
 * duplicating them, and running it twice changes nothing.
 *
 * That last property is the one that matters operationally. The Python machine rewrites these
 * files every day, so the import runs repeatedly against overlapping data; if a second run
 * were merely "harmless" rather than provably a no-op, duplicate messages would accumulate
 * and the follow-up sequence would lose its position.
 */

const SENDER = "jackhuhmate@gmail.com";

const LEADS_CSV = [
  "Business Name,Trade,London Area,Phone,Email,Website,Website Score,Biggest Flaw,Group",
  '1st Plumbers,Plumber,Walthamstow,020 8166 9967,info@1st-plumbers.co.uk,https://www.1st-plumbers.co.uk/,4,"Frozen at 2021, and the copy is keyword-stuffed",A',
  "Bromley Roofer Ltd,Roofer,Bromley,020 7000 1111,bromleyrooferltd@gmail.com,,,No website at all,B",
  "Farrants Flooring,Flooring,Croydon,,info@farrantsflooring.co.uk,http://farrantsflooring.co.uk,6,Not mobile friendly,A",
  "Top Dog Joinery,Joiner,Ealing,020 9999 0000,john@topdogjoinery.co.uk,,,No website at all,B",
].join("\n");

/** One declared column, two cells per row — the shape the live file actually has. */
const DO_NOT_CONTACT_CSV = [
  "email",
  "john@topdogjoinery.co.uk,opted out 2026-07-28",
].join("\n");

const SENT_LOG_CSV = [
  "Business Name,Trade,London Area,Phone,Email,Website,Biggest Flaw,Email Subject,Date Sent,Status",
  "1st Plumbers,Plumber,Walthamstow,020 8166 9967,info@1st-plumbers.co.uk,https://www.1st-plumbers.co.uk/,Frozen at 2021,Your Walthamstow site still says 2021,2026-07-26,Sent",
  "Bromley Roofer Ltd,Roofer,Bromley,020 7000 1111,bromleyrooferltd@gmail.com,,No website at all,A site for Bromley Roofer,2026-07-26,Sent",
  "Farrants Flooring,Flooring,Croydon,,info@farrantsflooring.co.uk,http://farrantsflooring.co.uk,Not mobile friendly,Your flooring site on mobile,2026-07-27,Sent",
  // Not a send. A record of a decision not to send, and must not become a message.
  "Walthamstow Electricians,Electrician,Walthamstow,020 8166 9967,,https://walthamstow-electricians.co.uk/,Frozen footer,Your Walthamstow site still says 2021,2026-07-26,Skipped - No Email Found",
].join("\n");

/** No area column: these rows can only be resolved by email address. */
const FOLLOWUPS_LOG_CSV = [
  "business,email,touch,date",
  "1st Plumbers,info@1st-plumbers.co.uk,1,2026-07-29",
  "1st Plumbers,info@1st-plumbers.co.uk,2,2026-07-31",
].join("\n");

const REPLIES_LOG_CSV = [
  "business,email,category,action,date",
  "Bromley Roofer Ltd,bromleyrooferltd@gmail.com,Interested,Auto-replied with price: 449 build + 39/mo care plan; awaiting go-ahead,2026-07-26",
  // A raw From header in the name column, and a category in a different case.
  "Farrants Flooring <info@farrantsflooring.co.uk>,info@farrantsflooring.co.uk,OBJECTION,Auto-replied,2026-07-28",
].join("\n");

const PAYMENTS_CSV = ["date,business,amount_gbp,type,status,notes"].join("\n");

function fixtures(): CsvFiles {
  return {
    "leads.csv": LEADS_CSV,
    "do_not_contact.csv": DO_NOT_CONTACT_CSV,
    "sent_log.csv": SENT_LOG_CSV,
    "followups_log.csv": FOLLOWUPS_LOG_CSV,
    "replies_log.csv": REPLIES_LOG_CSV,
    "payments.csv": PAYMENTS_CSV,
  };
}

async function counts(db: TestDatabase): Promise<Record<string, number>> {
  const tables = {
    businesses,
    contacts,
    leads,
    siteAudits,
    conversations,
    messages,
    suppressions,
    events,
    customers,
    subscriptions,
    payments,
  };

  const result: Record<string, number> = {};
  for (const [name, table] of Object.entries(tables)) {
    const rows = await db.select().from(table);
    result[name] = rows.length;
  }
  return result;
}

describe("importAll", () => {
  let handle: TestDatabaseHandle;
  let ctx: ImportContext;

  beforeEach(async () => {
    handle = await createTestDatabase();
    ctx = { db: handle.db, logger: memoryLogger(), senderAddress: SENDER };
  });

  afterEach(async () => {
    await handle.close();
  });

  it("fans one lead row out into the tables that replace the CSV", async () => {
    await importAll(ctx, { "leads.csv": LEADS_CSV });

    const business = await handle.db.select().from(businesses);
    expect(business).toHaveLength(4);

    const plumber = business.find((row) => row.name === "1st Plumbers");
    expect(plumber).toBeDefined();
    expect(plumber?.source).toBe("csv_import");
    expect(plumber?.websiteHost).toBe("1st-plumbers.co.uk");
    expect(plumber?.area).toBe("Walthamstow");

    // Email and phone become separate contact rows; the CSV could only hold one of each.
    const plumberContacts = (await handle.db.select().from(contacts)).filter(
      (row) => row.businessId === plumber?.id,
    );
    expect(plumberContacts.map((row) => row.kind).sort()).toEqual(["email", "phone"]);
    expect(plumberContacts.find((row) => row.kind === "phone")?.valueNormalised).toBe(
      "02081669967",
    );

    // A lead exists for every business, and the audit that produced the pitch is recorded.
    expect(await handle.db.select().from(leads)).toHaveLength(4);
    const audits = await handle.db.select().from(siteAudits);
    expect(audits.find((row) => row.businessId === plumber?.id)?.score).toBe(4);
  });

  it("refuses to invent a business a log file mentions without an area", async () => {
    await importAll(ctx, fixtures());

    // The whole point of email-first resolution: `followups_log.csv` and `replies_log.csv`
    // carry no area, so name-only keying would have created shadow copies here.
    const all = await handle.db.select().from(businesses);
    expect(all).toHaveLength(4);
    expect(all.filter((row) => row.name === "1st Plumbers")).toHaveLength(1);
    expect(all.filter((row) => row.name === "Farrants Flooring")).toHaveLength(1);
  });

  it("records only real sends as messages, and counts the rest as ignored", async () => {
    const result = await importAll(ctx, {
      "leads.csv": LEADS_CSV,
      "sent_log.csv": SENT_LOG_CSV,
    });

    const sent = result.reports.find((report) => report.source === "sent_log.csv");
    expect(sent?.stats.inserted).toBe(3);
    // "Skipped - No Email Found" is a faithful record of a non-send, not a defect.
    expect(sent?.stats.ignored).toBe(1);
    expect(sent?.stats.skipped).toBe(0);

    const outbound = await handle.db.select().from(messages);
    expect(outbound).toHaveLength(3);
    expect(outbound.every((row) => row.direction === "outbound")).toBe(true);
    expect(outbound.every((row) => row.fromAddress === SENDER)).toBe(true);
    // The log records that a send happened, never its text.
    expect(outbound.every((row) => row.body === "")).toBe(true);
  });

  it("carries the follow-up sequence position onto the lead", async () => {
    await importAll(ctx, {
      "leads.csv": LEADS_CSV,
      "sent_log.csv": SENT_LOG_CSV,
      "followups_log.csv": FOLLOWUPS_LOG_CSV,
    });

    const plumber = (await handle.db.select().from(businesses)).find(
      (row) => row.name === "1st Plumbers",
    );
    const lead = (await handle.db.select().from(leads)).find(
      (row) => row.businessId === plumber?.id,
    );

    // Two touches, and the highest wins regardless of row order — this is what stops a
    // fourth chase being licensed by re-importing.
    expect(lead?.followUpsSent).toBe(2);
    expect(lead?.status).toBe("following_up");
    expect(lead?.lastContactedAt).toEqual(new Date("2026-07-31T00:00:00.000Z"));
  });

  it("classifies replies, advances the lead and stops the automated chase", async () => {
    await importAll(ctx, fixtures());

    const bromley = (await handle.db.select().from(businesses)).find(
      (row) => row.name === "Bromley Roofer Ltd",
    );
    const lead = (await handle.db.select().from(leads)).find(
      (row) => row.businessId === bromley?.id,
    );

    expect(lead?.status).toBe("interested");
    expect(lead?.lastRepliedAt).toEqual(new Date("2026-07-26T00:00:00.000Z"));
    // A human is in the thread; the machine must not schedule another touch.
    expect(lead?.nextActionAt).toBeNull();

    const inbound = (await handle.db.select().from(messages)).filter(
      (row) => row.direction === "inbound",
    );
    expect(inbound).toHaveLength(2);
    expect(inbound.map((row) => row.intent).sort()).toEqual(["interested", "objection"]);
    expect(inbound.every((row) => row.isAutomated === false)).toBe(true);
  });

  it("never hands imported history to the outbox as new work", async () => {
    await importAll(ctx, fixtures());

    // The action column is preserved as an audit event...
    const recorded = await handle.db.select().from(events);
    expect(recorded).toHaveLength(2);
    expect(recorded.every((row) => row.type === "reply.handled")).toBe(true);

    // ...but already published, because the outbox queue is `where published_at is null` and
    // republishing a month-old auto-reply would email the business again.
    const unpublished = await handle.db
      .select()
      .from(events)
      .where(isNull(events.publishedAt));
    expect(unpublished).toHaveLength(0);
  });

  it("suppresses an opted-out address permanently", async () => {
    await importAll(ctx, fixtures());

    const blocked = await handle.db.select().from(suppressions);
    expect(blocked).toHaveLength(1);
    // Keyed on the normalised address, not on a lead: suppression must survive the lead
    // being pruned and must still match if the same address reappears under a new business.
    expect(blocked[0]?.kind).toBe("email");
    expect(blocked[0]?.valueNormalised).toBe("john@topdogjoinery.co.uk");
    expect(blocked[0]?.reason).toBe("opt_out_request");
    // The note travels in the second cell of a file that declares one column.
    expect(blocked[0]?.note).toContain("opted out");
  });

  it("changes nothing on a second run", async () => {
    const first = await importAll(ctx, fixtures());
    expect(first.totals.inserted).toBeGreaterThan(0);
    expect(first.totals.skipped).toBe(0);

    const before = await counts(handle.db);
    const second = await importAll(ctx, fixtures());
    const after = await counts(handle.db);

    // Not "harmless" — provably inert. Every row is accounted for as unchanged.
    expect(second.totals.inserted).toBe(0);
    expect(second.totals.updated).toBe(0);
    expect(second.totals.skipped).toBe(0);
    expect(after).toEqual(before);
  });

  it("reports a missing file instead of refusing to run", async () => {
    const result = await importAll(ctx, { "leads.csv": LEADS_CSV });

    expect(result.missing).toEqual([
      "do_not_contact.csv",
      "sent_log.csv",
      "followups_log.csv",
      "replies_log.csv",
      "payments.csv",
    ]);
    expect(result.reports).toHaveLength(1);
  });
});

describe("payments", () => {
  let handle: TestDatabaseHandle;
  let ctx: ImportContext;

  beforeEach(async () => {
    handle = await createTestDatabase();
    ctx = { db: handle.db, logger: memoryLogger(), senderAddress: SENDER };
  });

  afterEach(async () => {
    await handle.close();
  });

  it("creates the customer chain a payment implies", async () => {
    await importAll(ctx, {
      "leads.csv": LEADS_CSV,
      "payments.csv": [
        "date,business,amount_gbp,type,status,notes",
        "2026-08-01,1st Plumbers,449.00,build,paid,cash on completion",
        "2026-08-01,1st Plumbers,39.00,care,paid,first month",
      ].join("\n"),
    });

    const customer = await handle.db.select().from(customers);
    expect(customer).toHaveLength(1);

    const plumberLead = (await handle.db.select().from(leads)).find(
      (row) => row.id === customer[0]?.leadId,
    );
    expect(plumberLead?.status).toBe("won");

    const paid = await handle.db.select().from(payments);
    expect(paid).toHaveLength(2);
    expect(paid.map((row) => row.amountPence).sort((a, b) => a - b)).toEqual([
      3900, 44900,
    ]);
    expect(paid.every((row) => row.currency === "GBP")).toBe(true);

    // The care plan payment is attached to a subscription priced from the constant.
    const plan = await handle.db.select().from(subscriptions);
    expect(plan).toHaveLength(1);
    expect(plan[0]?.amountPence).toBe(3900);
  });

  it("refuses to guess at an unrecognised payment type", async () => {
    const result = await importAll(ctx, {
      "leads.csv": LEADS_CSV,
      "payments.csv": [
        "date,business,amount_gbp,type,status,notes",
        "2026-08-01,1st Plumbers,449.00,misc,paid,",
      ].join("\n"),
    });

    const report = result.reports.find((r) => r.source === "payments.csv");
    expect(report?.stats.inserted).toBe(0);
    expect(report?.stats.skipped).toBe(1);
    expect(report?.problems[0]).toContain("unrecognised payment type");
    expect(await handle.db.select().from(payments)).toHaveLength(0);
  });
});

describe("parseGbpToPence", () => {
  it("converts without floating point error", () => {
    // `449.50 * 100` is 44949.999… in binary floating point. A rounding error in a money
    // column is only ever found by a customer.
    expect(parseGbpToPence("449.50")).toBe(44_950);
    expect(parseGbpToPence("449")).toBe(44_900);
    expect(parseGbpToPence("£1,299.99")).toBe(129_999);
    expect(parseGbpToPence("39.9")).toBe(3990);
    expect(parseGbpToPence("-50.00")).toBe(-5000);
  });

  it("rejects anything that is not an amount", () => {
    expect(parseGbpToPence("")).toBeNull();
    expect(parseGbpToPence("tbc")).toBeNull();
    expect(parseGbpToPence("449.999")).toBeNull();
  });
});
