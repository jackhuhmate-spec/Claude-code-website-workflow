/**
 * Time as a dependency.
 *
 * Every deadline in this system is business-critical: the daily send cap resets at
 * midnight, a day-3 follow-up is due on day 3, and a subscription renews on a date. Code
 * that calls `Date.now()` directly cannot be tested without either sleeping or freezing the
 * machine clock, so the interesting cases — a run that straddles midnight, a follow-up due
 * exactly today — end up untested. Injecting the clock makes them ordinary unit tests.
 */
export interface Clock {
  now(): Date;
  /** Resolves after `ms`. Rejects if `signal` aborts first. */
  sleep(ms: number, signal?: AbortSignal): Promise<void>;
}

export const systemClock: Clock = {
  now: () => new Date(),
  sleep: (ms, signal) =>
    new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(signal.reason as Error);
        return;
      }
      const timer = setTimeout(() => {
        signal?.removeEventListener("abort", onAbort);
        resolve();
      }, ms);
      const onAbort = () => {
        clearTimeout(timer);
        reject(signal?.reason as Error);
      };
      signal?.addEventListener("abort", onAbort, { once: true });
    }),
};

/**
 * A clock under test control. `sleep` returns immediately and advances the clock, so a
 * retry policy with an hour of backoff runs in microseconds without faking timers.
 */
export class TestClock implements Clock {
  private current: Date;
  /** Every duration slept, in call order — assert on backoff without measuring wall time. */
  readonly slept: number[] = [];

  constructor(start: Date | string = "2026-01-01T00:00:00.000Z") {
    this.current = new Date(start);
  }

  now(): Date {
    return new Date(this.current);
  }

  sleep(ms: number, signal?: AbortSignal): Promise<void> {
    if (signal?.aborted) return Promise.reject(signal.reason as Error);
    this.slept.push(ms);
    this.advance(ms);
    return Promise.resolve();
  }

  advance(ms: number): void {
    this.current = new Date(this.current.getTime() + ms);
  }

  set(when: Date | string): void {
    this.current = new Date(when);
  }
}
