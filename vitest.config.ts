import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["packages/*/src/**/*.test.ts", "packages/*/test/**/*.test.ts"],
    // Integration tests spin up an in-process Postgres; give them room but never
    // let a hung connection hold CI open indefinitely.
    testTimeout: 30_000,
    hookTimeout: 60_000,
  },
});
