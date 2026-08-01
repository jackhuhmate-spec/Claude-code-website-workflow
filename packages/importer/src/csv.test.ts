import { ValidationError } from "@agency/shared";
import { describe, expect, it } from "vitest";
import { parseCsv, parseCsvTable } from "./csv.js";

describe("parseCsv", () => {
  it("keeps commas, quotes and newlines inside a quoted field", () => {
    // This is the real shape of `Biggest Flaw`, and the reason for a parser at all.
    const text = 'a,"copyright is frozen at 2021, and the page is ""padded""",c\n';

    expect(parseCsv(text)[0]?.cells).toEqual([
      "a",
      'copyright is frozen at 2021, and the page is "padded"',
      "c",
    ]);
  });

  it("keeps a newline inside a quoted field as part of the value", () => {
    const rows = parseCsv('name,note\n"A","line one\nline two"\n');

    expect(rows).toHaveLength(2);
    expect(rows[1]?.cells[1]).toBe("line one\nline two");
  });

  it("handles CRLF, a missing trailing newline and blank lines", () => {
    const rows = parseCsv("a,b\r\n1,2\r\n\r\n3,4");

    expect(rows.map((row) => row.cells)).toEqual([
      ["a", "b"],
      ["1", "2"],
      ["3", "4"],
    ]);
  });

  it("preserves empty fields rather than collapsing them", () => {
    // `leads.csv` leaves Email blank when none was verified. An off-by-one here would
    // shift a website URL into the email column and mail a URL.
    expect(parseCsv("a,,c\n")[0]?.cells).toEqual(["a", "", "c"]);
  });

  it("reports the line a record started on, counting quoted newlines", () => {
    const rows = parseCsv('h\n"multi\nline"\nlast\n');

    expect(rows[2]?.line).toBe(4);
  });

  it("refuses a file that ends inside a quoted field", () => {
    expect(() => parseCsv('a,"unterminated\n')).toThrow(ValidationError);
  });

  it("returns nothing for an empty file", () => {
    expect(parseCsv("")).toEqual([]);
    expect(parseCsv("\n")).toEqual([]);
  });
});

describe("parseCsvTable", () => {
  it("addresses cells by header, ignoring case and padding", () => {
    const table = parseCsvTable("Business Name, Email\nAcme,info@acme.test\n");

    expect(table.headers).toEqual(["Business Name", "Email"]);
    expect(table.records[0]?.get("business name")).toBe("Acme");
    expect(table.records[0]?.get("EMAIL")).toBe("info@acme.test");
  });

  it("keeps cells past the header, so a ragged file loses nothing", () => {
    // do_not_contact.csv: header `email`, rows `address,opted out 2026-07-28`.
    const table = parseCsvTable("email\njohn@example.test,opted out 2026-07-28\n");

    expect(table.records[0]?.get("email")).toBe("john@example.test");
    expect(table.records[0]?.extras).toEqual(["opted out 2026-07-28"]);
  });

  it("returns an empty string for a column the row does not reach", () => {
    const table = parseCsvTable("a,b,c\n1\n");

    expect(table.records[0]?.get("c")).toBe("");
  });

  it("returns an empty table for an empty file", () => {
    expect(parseCsvTable("")).toEqual({ headers: [], records: [] });
  });
});
