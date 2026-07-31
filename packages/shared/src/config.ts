import { z } from "zod";
import { ConfigError } from "./errors.js";
import type { LogLevel } from "./logger.js";

/**
 * Configuration loading.
 *
 * Two rules, both non-negotiable and both enforced here rather than trusted to reviewers:
 *
 * 1. **No credential is ever written in source.** Secrets arrive only through the
 *    environment, which is why this module is the single place that reads `process.env`.
 * 2. **Missing configuration fails at startup, not at first use.** A worker that boots
 *    happily and then throws at 10:01am — mid send window, after some mail has gone out —
 *    is far worse than one that refuses to start.
 */

export const logLevelSchema = z.enum([
  "trace",
  "debug",
  "info",
  "warn",
  "error",
  "fatal",
]) satisfies z.ZodType<LogLevel>;

/** Coerces the string forms an env var can actually take. `""` counts as unset. */
export const booleanFromEnv = z
  .string()
  .transform((v) => v.trim().toLowerCase())
  .pipe(z.enum(["true", "false", "1", "0", "yes", "no", ""]))
  .transform((v) => v === "true" || v === "1" || v === "yes");

export const intFromEnv = (min: number, max: number) =>
  z
    .string()
    .regex(/^\d+$/, "must be a whole number")
    .transform(Number)
    .pipe(z.number().int().min(min).max(max));

export const baseEnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  LOG_LEVEL: logLevelSchema.default("info"),
  LOG_PRETTY: booleanFromEnv.default(false),
});

export type BaseEnv = z.infer<typeof baseEnvSchema>;

export type EnvSource = Readonly<Record<string, string | undefined>>;

/**
 * Parse and validate an environment against a schema.
 *
 * The thrown `ConfigError` lists which variables are wrong and why, and deliberately never
 * echoes a value — the whole point of the exercise is that these are secrets, and a
 * "expected string, received nfp_xxx" message in a CI log defeats it entirely.
 */
export function loadConfig<T extends z.ZodType>(
  schema: T,
  source: EnvSource = process.env,
): z.output<T> {
  const result = schema.safeParse(source);
  if (result.success) return result.data;

  const problems = result.error.issues
    .map((issue) => {
      const path = issue.path.join(".") || "(root)";
      return `${path}: ${issue.message}`;
    })
    .sort();

  throw new ConfigError(
    "config.invalid",
    `Invalid configuration:\n  - ${problems.join("\n  - ")}`,
    { context: { problems } },
  );
}

/**
 * Read a required secret directly, for the few places that need one value rather than a
 * whole schema. Present but empty is treated as absent: a blank GitHub Actions secret is a
 * misconfiguration, and silently sending unauthenticated requests is the worse outcome.
 */
export function requireSecret(name: string, source: EnvSource = process.env): string {
  const value = source[name];
  if (value === undefined || value.trim() === "") {
    throw new ConfigError("config.missing_secret", `Missing required secret: ${name}`, {
      context: { name },
    });
  }
  return value;
}
