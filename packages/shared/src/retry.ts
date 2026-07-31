import type { Clock } from "./clock.js";
import { systemClock } from "./clock.js";
import type { AppError } from "./errors.js";
import { isRetryable, toAppError } from "./errors.js";
import type { Logger } from "./logger.js";

export interface RetryPolicy {
  /** Total attempts including the first. 1 disables retrying. */
  readonly attempts: number;
  /** Delay before attempt 2. Each subsequent delay multiplies by `factor`. */
  readonly baseDelayMs: number;
  readonly maxDelayMs: number;
  readonly factor: number;
  /**
   * Give up once this much time has elapsed, even with attempts remaining. A send window
   * is finite; a call that retries for 20 minutes has already failed in practice.
   */
  readonly maxElapsedMs: number;
}

/**
 * Sensible for a third-party HTTP call. Full-jitter backoff: 0–500ms, 0–1s, 0–2s, 0–4s.
 */
export const DEFAULT_RETRY: RetryPolicy = {
  attempts: 4,
  baseDelayMs: 500,
  maxDelayMs: 30_000,
  factor: 2,
  maxElapsedMs: 120_000,
};

/**
 * Sending is not idempotent. A retry that duplicates a cold email is worse than a retry
 * that fails, so one cautious retry only — enough to survive a dropped connection, not
 * enough to mail somebody twice if the failure came after the message was accepted.
 */
export const SEND_RETRY: RetryPolicy = {
  attempts: 2,
  baseDelayMs: 2_000,
  maxDelayMs: 10_000,
  factor: 2,
  maxElapsedMs: 30_000,
};

export interface RetryOptions {
  readonly policy?: RetryPolicy;
  readonly clock?: Clock;
  readonly logger?: Logger;
  /** Label used in logs, e.g. `netlify.createSite`. */
  readonly operation: string;
  readonly signal?: AbortSignal;
  /** Injected for deterministic jitter under test. */
  readonly random?: () => number;
}

/**
 * Full jitter: a uniformly random delay in `[0, exponentialBackoff]`.
 *
 * Equal-jitter and no-jitter both leave callers synchronised, so a rate limit that trips
 * several workers at once has them all retry at the same instant and trip it again.
 */
export function backoffDelayMs(
  attempt: number,
  policy: RetryPolicy,
  random: () => number,
): number {
  const exponential = policy.baseDelayMs * Math.pow(policy.factor, attempt - 1);
  return Math.round(random() * Math.min(exponential, policy.maxDelayMs));
}

/**
 * Run `fn`, retrying only errors that declare themselves retryable.
 *
 * The last error is always rethrown rather than wrapped, so the caller sees the real cause
 * and its `code` rather than a generic "retries exhausted".
 */
export async function retry<T>(
  fn: (attempt: number) => Promise<T>,
  options: RetryOptions,
): Promise<T> {
  const policy = options.policy ?? DEFAULT_RETRY;
  const clock = options.clock ?? systemClock;
  const random = options.random ?? Math.random;
  const startedAt = clock.now().getTime();

  let lastError: AppError | undefined;

  for (let attempt = 1; attempt <= policy.attempts; attempt += 1) {
    options.signal?.throwIfAborted();
    try {
      return await fn(attempt);
    } catch (caught: unknown) {
      const error = toAppError(caught, `${options.operation}.failed`);
      lastError = error;

      const isLastAttempt = attempt === policy.attempts;
      if (!isRetryable(error) || isLastAttempt) throw error;

      // An upstream that tells us how long to wait always wins over our own guess.
      const delay = error.retryAfterMs ?? backoffDelayMs(attempt, policy, random);
      const elapsed = clock.now().getTime() - startedAt;
      if (elapsed + delay > policy.maxElapsedMs) {
        options.logger?.warn(
          { ...error.toLogObject(), operation: options.operation, attempt, elapsed },
          "retry budget exhausted",
        );
        throw error;
      }

      options.logger?.warn(
        { ...error.toLogObject(), operation: options.operation, attempt, delay },
        "retrying after failure",
      );
      await clock.sleep(delay, options.signal);
    }
  }

  // Unreachable: the loop either returns or throws. Kept so the function is total.
  throw lastError ?? toAppError(undefined, `${options.operation}.failed`);
}
