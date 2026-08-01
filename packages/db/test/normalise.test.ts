import { describe, expect, it } from "vitest";
import {
  normaliseEmail,
  normaliseHost,
  normaliseName,
  normalisePhone,
} from "../src/normalise.js";

describe("normaliseEmail", () => {
  it("folds case and trims, so a suppression cannot be bypassed by capitalisation", () => {
    expect(normaliseEmail("  John@TopDogJoinery.co.uk ")).toBe(
      "john@topdogjoinery.co.uk",
    );
  });

  it("leaves dots and plus tags alone", () => {
    // Stripping them would merge mailboxes that are genuinely separate on most providers.
    expect(normaliseEmail("first.last+quotes@example.com")).toBe(
      "first.last+quotes@example.com",
    );
  });
});

describe("normalisePhone", () => {
  it("treats spaced, international and bare forms as one number", () => {
    expect(normalisePhone("020 8166 9967")).toBe("02081669967");
    expect(normalisePhone("+44 20 8166 9967")).toBe("02081669967");
    expect(normalisePhone("(020) 8166-9967")).toBe("02081669967");
  });

  it("does not mangle a short number that merely starts with 44", () => {
    expect(normalisePhone("4412")).toBe("4412");
  });
});

describe("normaliseName", () => {
  it("folds case, punctuation and spacing", () => {
    expect(normaliseName("  A&B  Plumbing (London) ")).toBe("a b plumbing london");
  });

  it("keeps legal suffixes, because merging two real businesses is unrecoverable", () => {
    expect(normaliseName("Smith Roofing")).not.toBe(normaliseName("Smith Roofing Ltd"));
  });
});

describe("normaliseHost", () => {
  it("strips scheme, www and path", () => {
    expect(normaliseHost("https://www.Example.co.uk/about")).toBe("example.co.uk");
  });

  it("accepts a bare host", () => {
    expect(normaliseHost("example.co.uk")).toBe("example.co.uk");
  });

  it("returns null rather than guessing at rubbish", () => {
    expect(normaliseHost("")).toBeNull();
    expect(normaliseHost("   ")).toBeNull();
    expect(normaliseHost("http://")).toBeNull();
  });
});
