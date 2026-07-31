import { integer, timestamp } from "drizzle-orm/pg-core";

/**
 * Column helpers, so the conventions below are applied by construction rather than by
 * remembering them on every table.
 */

/**
 * All timestamps are `timestamptz`.
 *
 * The business runs on London time, which changes offset twice a year. A naive timestamp
 * makes "sent today" ambiguous for one hour every October and silently wrong for the daily
 * send cap. Store instants; convert at the edge.
 */
export const timestampTz = (name: string) =>
  timestamp(name, { withTimezone: true, mode: "date" });

export const createdAt = () => timestampTz("created_at").notNull().defaultNow();
export const updatedAt = () => timestampTz("updated_at").notNull().defaultNow();

/**
 * Money is stored in pence as an integer, never as a float.
 *
 * £449 and £39/month are fixed prices, and binary floating point cannot represent either
 * exactly. Integer pence removes the entire class of rounding disputes with a customer.
 */
export const pence = (name: string) => integer(name);
