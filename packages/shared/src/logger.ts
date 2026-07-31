import { pino } from "pino";
import { isAppError } from "./errors.js";

/**
 * The logging surface the rest of the system is allowed to depend on.
 *
 * Deliberately narrower than pino's own type. Use-cases should not be able to reach for
 * transports, flush behaviour or level manipulation, and keeping the interface small means
 * pino can be replaced without touching a single call site.
 */
export interface Logger {
  trace(obj: object, msg?: string): void;
  debug(obj: object, msg?: string): void;
  info(obj: object, msg?: string): void;
  warn(obj: object, msg?: string): void;
  error(obj: object, msg?: string): void;
  fatal(obj: object, msg?: string): void;
  /** Returns a logger that stamps `bindings` onto every subsequent line. */
  child(bindings: Record<string, unknown>): Logger;
}

export type LogLevel = "trace" | "debug" | "info" | "warn" | "error" | "fatal";

/**
 * Keys whose values are never safe to log, at any depth.
 *
 * This list is a control, not a convenience. A live Netlify token sat in this repository's
 * git history for weeks because a secret was written somewhere it did not belong; the
 * equivalent mistake in logs is easier to make and harder to notice, because logs are
 * shipped, aggregated and retained by default.
 */
const SECRET_KEYS: ReadonlySet<string> = new Set([
  "password",
  "passwd",
  "apppassword",
  "gmailapppassword",
  "token",
  "accesstoken",
  "refreshtoken",
  "apikey",
  "api_key",
  "secret",
  "clientsecret",
  "authorization",
  "cookie",
  "setcookie",
  "sessionid",
  "privatekey",
  "netlifytoken",
  "groqapikey",
  "githubtoken",
  "databaseurl",
  "connectionstring",
  "dsn",
]);

const CENSOR = "[redacted]";

/**
 * Personal data we log by identifier, not by value.
 *
 * These are business contacts under UK GDPR. Logs are the easiest place for their data to
 * leak into a third-party aggregator, so an email address is truncated to its domain and a
 * message body is replaced by its length — enough to debug delivery, not enough to rebuild
 * the mailing list from log storage.
 */
const PII_KEYS: ReadonlySet<string> = new Set([
  "email",
  "to",
  "from",
  "recipient",
  "phone",
]);
const BODY_KEYS: ReadonlySet<string> = new Set([
  "body",
  "html",
  "text",
  "subject",
  "prompt",
]);

export function maskEmail(value: string): string {
  const at = value.lastIndexOf("@");
  if (at <= 0) return CENSOR;
  return `***@${value.slice(at + 1)}`;
}

/**
 * Recursively redact secrets and reduce personal data before anything reaches a transport.
 *
 * Done as a pino serializer rather than with `redact` paths because the paths approach
 * requires knowing the shape of every object ever logged, and the one nobody predicted is
 * exactly the one that leaks.
 */
export function redact(value: unknown, depth = 0): unknown {
  if (depth > 8) return "[truncated]";
  if (value === null || typeof value !== "object") return value;
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value)) return value.map((item) => redact(item, depth + 1));
  if (value instanceof Error) return serialiseError(value);

  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    const normalised = key.toLowerCase().replace(/[_-]/g, "");
    if (SECRET_KEYS.has(normalised)) {
      out[key] = CENSOR;
    } else if (typeof item === "string" && PII_KEYS.has(normalised)) {
      out[key] = maskEmail(item);
    } else if (typeof item === "string" && BODY_KEYS.has(normalised)) {
      out[key] = `[${item.length} chars]`;
    } else {
      out[key] = redact(item, depth + 1);
    }
  }
  return out;
}

function serialiseError(error: Error): Record<string, unknown> {
  const base = isAppError(error)
    ? error.toLogObject()
    : { name: error.name, message: error.message };
  return {
    ...(redact(base, 1) as Record<string, unknown>),
    ...(error.stack === undefined ? {} : { stack: error.stack }),
    ...(error.cause === undefined ? {} : { cause: redact(error.cause, 1) }),
  };
}

export interface LoggerOptions {
  readonly level?: LogLevel;
  readonly service: string;
  /** Human-readable output for a terminal. JSON otherwise, which is what shippers want. */
  readonly pretty?: boolean;
  readonly bindings?: Record<string, unknown>;
}

export function createLogger(options: LoggerOptions): Logger {
  return pino({
    level: options.level ?? "info",
    base: { service: options.service, ...options.bindings },
    // ISO timestamps: log aggregators and humans both read them, unlike epoch millis.
    timestamp: pino.stdTimeFunctions.isoTime,
    formatters: {
      level: (label) => ({ level: label }),
      log: (object) => redact(object) as Record<string, unknown>,
    },
    serializers: { err: serialiseError, error: serialiseError },
    ...(options.pretty === true
      ? { transport: { target: "pino-pretty", options: { colorize: true } } }
      : {}),
  }) satisfies Logger;
}

export interface CapturedLine {
  readonly level: LogLevel;
  readonly obj: Record<string, unknown>;
  readonly msg: string | undefined;
}

/**
 * An in-memory logger for tests: assert that something was logged, and that a secret was
 * not, without a transport or a temp file.
 */
export function memoryLogger(lines: CapturedLine[] = []): Logger & {
  readonly lines: CapturedLine[];
} {
  const make = (bindings: Record<string, unknown>): Logger => {
    const write = (level: LogLevel) => (obj: object, msg?: string) => {
      lines.push({
        level,
        obj: redact({ ...bindings, ...obj }) as Record<string, unknown>,
        msg,
      });
    };
    return {
      trace: write("trace"),
      debug: write("debug"),
      info: write("info"),
      warn: write("warn"),
      error: write("error"),
      fatal: write("fatal"),
      child: (extra) => make({ ...bindings, ...extra }),
    };
  };
  return Object.assign(make({}), { lines });
}
