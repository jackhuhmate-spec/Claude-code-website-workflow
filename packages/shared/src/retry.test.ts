import { describe, expect, it, vi } from "vitest";
import { TestClock } from "./clock.js";
import {
  InternalError,
  PolicyViolationError,
  RateLimitError,
  UpstreamError,
} from "./errors.js";
import { backoffDelayMs, retry, SEND_RETRY, type RetryPolicy } from "./retry.js";

const POLICY: RetryPolicy = {
  attempts: 4,
  baseDelayMs: 100,
  maxDelayMs: 10_000,
  factor: 2,
  maxElapsedMs: 60_000,
};

/** Full jitter at its maximum, so delays are exact and assertable. */
const noJitter = () => 1;

describe("retry", () => {
  it("returns the first success without sleeping", async () => {
    const clock = new TestClock();
    const fn = vi.fn().mockResolvedValue("ok");
    await expect(retry(fn, { operation: "x", clock, policy: POLICY })).resolves.toBe(
      "ok",
    );
    expect(fn).toHaveBeenCalledTimes(1);
    expect(clock.slept).toEqual([]);
  });

  it("retries a transient failure and succeeds", async () => {
    const clock = new TestClock();
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new UpstreamError("api.502", "bad gateway"))
      .mockResolvedValue("ok");
    await expect(
      retry(fn, { operation: "x", clock, policy: POLICY, random: noJitter }),
    ).resolves.toBe("ok");
    expect(fn).toHaveBeenCalledTimes(2);
    expect(clock.slept).toEqual([100]);
  });

  it("backs off exponentially, then rethrows the real error", async () => {
    const clock = new TestClock();
    const error = new UpstreamError("api.502", "bad gateway");
    const fn = vi.fn().mockRejectedValue(error);

    await expect(
      retry(fn, { operation: "x", clock, policy: POLICY, random: noJitter }),
    ).rejects.toBe(error); // the caller sees the cause, not "retries exhausted"

    expect(fn).toHaveBeenCalledTimes(4);
    expect(clock.slept).toEqual([100, 200, 400]);
  });

  it("gives up immediately on a non-retryable error", async () => {
    const clock = new TestClock();
    const fn = vi
      .fn()
      .mockRejectedValue(new PolicyViolationError("email.opted_out", "no"));
    await expect(retry(fn, { operation: "x", clock, policy: POLICY })).rejects.toThrow(
      PolicyViolationError,
    );
    expect(fn).toHaveBeenCalledTimes(1);
    expect(clock.slept).toEqual([]);
  });

  it("honours retryAfterMs over its own backoff", async () => {
    const clock = new TestClock();
    const fn = vi
      .fn()
      .mockRejectedValueOnce(
        new RateLimitError("gmail.429", "slow down", { retryAfterMs: 5_000 }),
      )
      .mockResolvedValue("ok");
    await expect(
      retry(fn, { operation: "x", clock, policy: POLICY, random: noJitter }),
    ).resolves.toBe("ok");
    expect(clock.slept).toEqual([5_000]);
  });

  it("stops once the elapsed budget would be exceeded", async () => {
    // A send window is finite. Attempts remaining is not a reason to keep waiting.
    const clock = new TestClock();
    const fn = vi.fn().mockRejectedValue(new UpstreamError("api.502", "bad gateway"));
    const policy: RetryPolicy = { ...POLICY, maxElapsedMs: 250 };

    await expect(
      retry(fn, { operation: "x", clock, policy, random: noJitter }),
    ).rejects.toThrow(UpstreamError);

    expect(clock.slept).toEqual([100]); // 100 + 200 would breach 250, so it stops
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("does not retry a bare TypeError from our own code", async () => {
    const clock = new TestClock();
    const native = new TypeError("undefined is not a function");
    const fn = vi.fn().mockRejectedValue(native);

    // Classified as `internal` and therefore not retried — a defect in our own code will
    // not fix itself on the third attempt. It is wrapped so every failure carries the
    // taxonomy, but the original is kept as `cause` so the stack is never lost.
    const caught = await retry(fn, { operation: "x", clock, policy: POLICY }).catch(
      (e: unknown) => e,
    );

    expect(caught).toBeInstanceOf(InternalError);
    expect((caught as InternalError).kind).toBe("internal");
    expect((caught as InternalError).cause).toBe(native);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(clock.slept).toEqual([]);
  });

  it("aborts without another attempt when the signal fires", async () => {
    const clock = new TestClock();
    const controller = new AbortController();
    const fn = vi.fn().mockImplementation(() => {
      controller.abort();
      return Promise.reject(new UpstreamError("api.502", "bad gateway"));
    });

    await expect(
      retry(fn, {
        operation: "x",
        clock,
        policy: POLICY,
        signal: controller.signal,
        random: noJitter,
      }),
    ).rejects.toThrow();
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("sends at most twice, because sending is not idempotent", async () => {
    // A retry that duplicates a cold email is worse than a retry that fails.
    const clock = new TestClock();
    const fn = vi.fn().mockRejectedValue(new UpstreamError("smtp.dropped", "connection"));
    await expect(
      retry(fn, { operation: "send", clock, policy: SEND_RETRY, random: noJitter }),
    ).rejects.toThrow();
    expect(fn).toHaveBeenCalledTimes(2);
  });
});

describe("backoffDelayMs", () => {
  it("scales exponentially and clamps at maxDelayMs", () => {
    expect(backoffDelayMs(1, POLICY, noJitter)).toBe(100);
    expect(backoffDelayMs(2, POLICY, noJitter)).toBe(200);
    expect(backoffDelayMs(8, POLICY, noJitter)).toBe(10_000);
  });

  it("applies full jitter so concurrent workers do not resynchronise", () => {
    expect(backoffDelayMs(3, POLICY, () => 0)).toBe(0);
    expect(backoffDelayMs(3, POLICY, () => 0.5)).toBe(200);
    expect(backoffDelayMs(3, POLICY, () => 1)).toBe(400);
  });
});
