import { describe, expect, it } from "vitest";
import { z } from "zod";
import {
  baseEnvSchema,
  booleanFromEnv,
  intFromEnv,
  loadConfig,
  requireSecret,
} from "./config.js";
import { ConfigError } from "./errors.js";

describe("loadConfig", () => {
  it("applies defaults for optional settings", () => {
    expect(loadConfig(baseEnvSchema, {})).toEqual({
      NODE_ENV: "development",
      LOG_LEVEL: "info",
      LOG_PRETTY: false,
    });
  });

  it("fails at startup rather than at first use", () => {
    const schema = baseEnvSchema.extend({ DATABASE_URL: z.string().min(1) });
    expect(() => loadConfig(schema, {})).toThrow(ConfigError);
  });

  it("names every invalid variable, not just the first", () => {
    const schema = z.object({
      DATABASE_URL: z.string().min(1),
      SEND_CAP: intFromEnv(1, 100),
    });
    try {
      loadConfig(schema, { SEND_CAP: "not-a-number" });
      expect.unreachable("should have thrown");
    } catch (error) {
      expect(error).toBeInstanceOf(ConfigError);
      const problems = (error as ConfigError).context["problems"] as string[];
      expect(problems.join(" ")).toContain("DATABASE_URL");
      expect(problems.join(" ")).toContain("SEND_CAP");
    }
  });

  it("never echoes the offending value", () => {
    // A "received nfp_xxx" message in a CI log defeats the entire point of secrets.
    const schema = z.object({ NETLIFY_TOKEN: z.string().min(50) });
    try {
      loadConfig(schema, { NETLIFY_TOKEN: "nfp_shortbutsecret" });
      expect.unreachable("should have thrown");
    } catch (error) {
      expect((error as ConfigError).message).not.toContain("nfp_shortbutsecret");
    }
  });
});

describe("requireSecret", () => {
  it("returns the value when set", () => {
    expect(requireSecret("A", { A: "value" })).toBe("value");
  });

  it("treats blank as missing", () => {
    // A blank GitHub Actions secret is a misconfiguration; sending unauthenticated
    // requests instead is the worse outcome.
    expect(() => requireSecret("A", { A: "   " })).toThrow(ConfigError);
    expect(() => requireSecret("A", {})).toThrow(ConfigError);
  });

  it("does not leak the value in the error", () => {
    expect(() => requireSecret("NETLIFY_TOKEN", {})).toThrow(/Missing required secret/);
  });
});

describe("env coercion", () => {
  it("reads the string forms a boolean env var actually takes", () => {
    for (const truthy of ["true", "TRUE", "1", "yes"]) {
      expect(booleanFromEnv.parse(truthy)).toBe(true);
    }
    for (const falsy of ["false", "0", "no", ""]) {
      expect(booleanFromEnv.parse(falsy)).toBe(false);
    }
  });

  it("rejects a non-numeric integer rather than coercing it to NaN", () => {
    expect(() => intFromEnv(1, 100).parse("thirty")).toThrow();
    expect(() => intFromEnv(1, 100).parse("101")).toThrow();
    expect(intFromEnv(1, 100).parse("30")).toBe(30);
  });
});
