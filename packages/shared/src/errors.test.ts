import { describe, expect, it } from "vitest";
import {
  AppError,
  ConfigError,
  PolicyViolationError,
  RateLimitError,
  UpstreamError,
  ValidationError,
  isRetryable,
  toAppError,
} from "./errors.js";

describe("retryability", () => {
  it("treats transient upstream failures as retryable", () => {
    expect(isRetryable(new UpstreamError("netlify.deploy_failed", "502"))).toBe(true);
    expect(isRetryable(new RateLimitError("gmail.rate_limited", "slow down"))).toBe(true);
  });

  it("never retries a caller's own mistake", () => {
    expect(isRetryable(new ValidationError("lead.no_email", "missing email"))).toBe(
      false,
    );
    expect(isRetryable(new ConfigError("config.missing", "no token"))).toBe(false);
  });

  it("never retries a policy violation", () => {
    // Retrying "this address opted out" would mean mailing them again, which is the
    // breach itself. This must stay false regardless of what any caller asks for.
    const error = new PolicyViolationError("email.opted_out", "on the suppression list");
    expect(isRetryable(error)).toBe(false);
  });

  it("does not retry unknown thrown values", () => {
    // A TypeError from our own code will not fix itself on the third attempt.
    expect(isRetryable(new TypeError("x is not a function"))).toBe(false);
    expect(isRetryable("boom")).toBe(false);
    expect(isRetryable(undefined)).toBe(false);
  });

  it("lets an error override the default for its kind", () => {
    const error = new UpstreamError("smtp.rejected", "550 recipient rejected", {
      retryable: false, // a permanent SMTP rejection is not worth four attempts
    });
    expect(isRetryable(error)).toBe(false);
  });
});

describe("toAppError", () => {
  it("returns an AppError unchanged", () => {
    const original = new ValidationError("a.b", "nope");
    expect(toAppError(original)).toBe(original);
  });

  it("preserves a native Error as the cause", () => {
    const native = new TypeError("bad");
    const wrapped = toAppError(native, "worker.tick");
    expect(wrapped.kind).toBe("internal");
    expect(wrapped.code).toBe("worker.tick");
    expect(wrapped.message).toBe("bad");
    expect(wrapped.cause).toBe(native);
  });

  it("does not lose a non-Error throw", () => {
    const wrapped = toAppError({ weird: true }, "x");
    expect(wrapped.message).toContain('{"weird":true}');
    expect(wrapped.cause).toEqual({ weird: true });
  });

  it("survives a value that cannot be stringified", () => {
    const circular: Record<string, unknown> = {};
    circular["self"] = circular;
    expect(() => toAppError(circular)).not.toThrow();
  });
});

describe("toLogObject", () => {
  it("carries the taxonomy so logs are queryable by code and kind", () => {
    const error = new AppError("upstream", "groq.timeout", "took too long", {
      retryAfterMs: 1_000,
      context: { attempt: 2 },
    });
    expect(error.toLogObject()).toEqual({
      name: "AppError",
      kind: "upstream",
      code: "groq.timeout",
      message: "took too long",
      retryable: true,
      retryAfterMs: 1_000,
      context: { attempt: 2 },
    });
  });

  it("reports the subclass name", () => {
    expect(new ValidationError("a", "b").toLogObject()["name"]).toBe("ValidationError");
  });
});
