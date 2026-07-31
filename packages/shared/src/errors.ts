/**
 * Error taxonomy.
 *
 * The single design decision here is that **retryability is a property of the error, not
 * of the call site**. A caller wrapping an operation in `retry()` cannot know whether a
 * failure was a transient upstream blip or a permanently rejected recipient; the code that
 * raised it always can. Encoding it on the error means the retry policy needs no knowledge
 * of any specific integration, and a new adapter cannot accidentally cause a permanent
 * failure to be hammered 5 times — or a transient one to be dropped after one attempt.
 */

/** Broad class of failure. Drives retry, alerting and HTTP status mapping. */
export type ErrorKind =
  /** Input failed validation before anything was attempted. Never retryable. */
  | "validation"
  /** A required record does not exist. Never retryable. */
  | "not_found"
  /** State changed underneath us; the caller may be able to re-read and retry. */
  | "conflict"
  /** Misconfiguration or a missing secret. Never retryable — a human must act. */
  | "config"
  /** A third party failed. Usually retryable. */
  | "upstream"
  /** A third party asked us to slow down. Retryable, honouring `retryAfterMs`. */
  | "rate_limit"
  /** We gave up waiting. Retryable. */
  | "timeout"
  /**
   * A business rule forbids this action — mailing an opt-out, quoting a price in a cold
   * email, deploying a final site for an unpaid lead. Never retryable, and never
   * swallowed: a policy violation is a bug in the caller, not a runtime condition.
   */
  | "policy"
  /** Unclassified. Treated as a defect and never retried. */
  | "internal";

/** Whether a given kind may be retried when the error does not say otherwise. */
const RETRYABLE_BY_DEFAULT: Readonly<Record<ErrorKind, boolean>> = {
  validation: false,
  not_found: false,
  conflict: true,
  config: false,
  upstream: true,
  rate_limit: true,
  timeout: true,
  policy: false,
  internal: false,
};

export interface AppErrorOptions {
  /**
   * Structured detail for logs. Must not contain secrets or full message bodies —
   * pass identifiers, not payloads.
   */
  readonly context?: Readonly<Record<string, unknown>>;
  readonly cause?: unknown;
  /** Overrides the default retryability for the kind. Use sparingly and comment why. */
  readonly retryable?: boolean;
  /** Honoured by the retry policy when the upstream told us how long to wait. */
  readonly retryAfterMs?: number;
}

export class AppError extends Error {
  readonly kind: ErrorKind;
  /** Stable, machine-readable identifier, e.g. `email.recipient_not_contacted`. */
  readonly code: string;
  readonly retryable: boolean;
  readonly retryAfterMs: number | undefined;
  readonly context: Readonly<Record<string, unknown>>;

  constructor(
    kind: ErrorKind,
    code: string,
    message: string,
    options: AppErrorOptions = {},
  ) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = new.target.name;
    this.kind = kind;
    this.code = code;
    this.retryable = options.retryable ?? RETRYABLE_BY_DEFAULT[kind];
    this.retryAfterMs = options.retryAfterMs;
    this.context = options.context ?? {};
  }

  /** Shape suitable for structured logging. Never includes a stack for expected errors. */
  toLogObject(): Record<string, unknown> {
    return {
      name: this.name,
      kind: this.kind,
      code: this.code,
      message: this.message,
      retryable: this.retryable,
      ...(this.retryAfterMs === undefined ? {} : { retryAfterMs: this.retryAfterMs }),
      ...(Object.keys(this.context).length === 0 ? {} : { context: this.context }),
    };
  }
}

export class ValidationError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("validation", code, message, options);
  }
}

export class NotFoundError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("not_found", code, message, options);
  }
}

export class ConflictError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("conflict", code, message, options);
  }
}

export class ConfigError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("config", code, message, options);
  }
}

export class UpstreamError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("upstream", code, message, options);
  }
}

export class RateLimitError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("rate_limit", code, message, options);
  }
}

export class TimeoutError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("timeout", code, message, options);
  }
}

/**
 * A business invariant was violated. These correspond to the numbered invariants in
 * ROADMAP.md, each of which exists because a real incident occurred.
 */
export class PolicyViolationError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("policy", code, message, options);
  }
}

export class InternalError extends AppError {
  constructor(code: string, message: string, options?: AppErrorOptions) {
    super("internal", code, message, options);
  }
}

export function isAppError(value: unknown): value is AppError {
  return value instanceof AppError;
}

/**
 * True when an unknown thrown value should be retried.
 *
 * Anything that is not an `AppError` is treated as a defect and **not** retried. A
 * `TypeError` from our own code will not fix itself on the third attempt, and retrying it
 * only delays the failure and multiplies the side effects that preceded it.
 */
export function isRetryable(value: unknown): boolean {
  return isAppError(value) && value.retryable;
}

/**
 * Wrap an unknown thrown value as an `AppError` without losing it.
 *
 * `catch` gives us `unknown`, and code that assumes `Error` there loses the original when
 * something throws a string or a plain object.
 */
export function toAppError(value: unknown, code = "unexpected"): AppError {
  if (isAppError(value)) return value;
  if (value instanceof Error) {
    return new InternalError(code, value.message, { cause: value });
  }
  return new InternalError(code, `Non-error thrown: ${describe(value)}`, {
    cause: value,
  });
}

function describe(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return Object.prototype.toString.call(value);
  }
}
