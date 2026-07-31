import { describe, expect, it } from "vitest";
import { UpstreamError } from "./errors.js";
import { maskEmail, memoryLogger, redact } from "./logger.js";

describe("redact", () => {
  it("censors secrets whatever the casing or separator", () => {
    const out = redact({
      apiKey: "gsk_live_value",
      API_KEY: "gsk_live_value",
      "netlify-token": "nfp_live_value",
      gmailAppPassword: "abcd efgh ijkl mnop",
      databaseUrl: "postgres://user:pw@host/db",
    }) as Record<string, string>;

    expect(Object.values(out)).toEqual([
      "[redacted]",
      "[redacted]",
      "[redacted]",
      "[redacted]",
      "[redacted]",
    ]);
  });

  it("censors secrets nested at depth", () => {
    // The object nobody predicted is exactly the one that leaks, so this cannot rely
    // on knowing the shape in advance.
    const out = redact({ a: { b: { c: { netlifyToken: "nfp_live" } } } });
    expect(JSON.stringify(out)).not.toContain("nfp_live");
    expect(JSON.stringify(out)).toContain("[redacted]");
  });

  it("reduces a contact's address to its domain", () => {
    const out = redact({ email: "owner@topdogjoinery.co.uk" }) as Record<string, string>;
    expect(out["email"]).toBe("***@topdogjoinery.co.uk");
  });

  it("replaces message bodies with their length", () => {
    const out = redact({ subject: "Your website", body: "x".repeat(400) }) as Record<
      string,
      string
    >;
    expect(out["body"]).toBe("[400 chars]");
    expect(out["subject"]).toBe("[12 chars]");
  });

  it("keeps ordinary operational fields intact", () => {
    const out = redact({ leadId: 42, status: "sent", attempt: 2 });
    expect(out).toEqual({ leadId: 42, status: "sent", attempt: 2 });
  });

  it("terminates on a self-referencing object", () => {
    const circular: Record<string, unknown> = { name: "loop" };
    circular["self"] = circular;
    expect(() => redact(circular)).not.toThrow();
    expect(JSON.stringify(redact(circular))).toContain("[truncated]");
  });

  it("serialises an AppError with its taxonomy", () => {
    const out = redact({ err: new UpstreamError("netlify.502", "bad gateway") }) as {
      err: Record<string, unknown>;
    };
    expect(out.err["code"]).toBe("netlify.502");
    expect(out.err["kind"]).toBe("upstream");
    expect(out.err["retryable"]).toBe(true);
  });
});

describe("maskEmail", () => {
  it("keeps the domain and drops the local part", () => {
    expect(maskEmail("jake@example.co.uk")).toBe("***@example.co.uk");
  });

  it("censors anything that is not an address", () => {
    expect(maskEmail("not-an-address")).toBe("[redacted]");
    expect(maskEmail("@leading")).toBe("[redacted]");
  });
});

describe("memoryLogger", () => {
  it("captures lines and redacts them like the real logger", () => {
    const log = memoryLogger();
    log.info({ leadId: 7, apiKey: "gsk_secret" }, "sent");
    expect(log.lines).toHaveLength(1);
    expect(log.lines[0]?.msg).toBe("sent");
    expect(log.lines[0]?.obj).toEqual({ leadId: 7, apiKey: "[redacted]" });
  });

  it("stamps child bindings onto every line", () => {
    const log = memoryLogger();
    log.child({ runId: "abc" }).warn({ attempt: 1 }, "retrying");
    expect(log.lines[0]?.obj).toEqual({ runId: "abc", attempt: 1 });
  });
});
