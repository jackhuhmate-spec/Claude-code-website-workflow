import { index, pgTable, text, uniqueIndex, uuid } from "drizzle-orm/pg-core";
import { createdAt, pence, timestampTz, updatedAt } from "./columns.js";
import { customers } from "./delivery.js";
import { paymentKindEnum, paymentStatusEnum, subscriptionStatusEnum } from "./enums.js";

/**
 * Pricing is fixed and is not the agents' to decide: £449 for the build, £39/month for the
 * optional care plan. These constants exist so no code path can invent a number, and are
 * exported in pence because that is how they are stored.
 *
 * Invariant 8: never discount below £449.
 */
export const BUILD_PRICE_PENCE = 44_900;
export const CARE_PLAN_PENCE_PER_MONTH = 3_900;
export const CURRENCY = "GBP";

/** The £39/month care plan. One active subscription per customer. */
export const subscriptions = pgTable(
  "subscriptions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    customerId: uuid("customer_id")
      .notNull()
      .references(() => customers.id, { onDelete: "cascade" }),
    status: subscriptionStatusEnum("status").notNull().default("active"),
    /** Stored per subscription rather than read from the constant, so a historical price
     * change never silently rewrites what an existing customer agreed to pay. */
    amountPence: pence("amount_pence").notNull().default(CARE_PLAN_PENCE_PER_MONTH),
    currency: text("currency").notNull().default(CURRENCY),
    startedAt: timestampTz("started_at").notNull().defaultNow(),
    nextBillingAt: timestampTz("next_billing_at"),
    cancelledAt: timestampTz("cancelled_at"),
    cancellationReason: text("cancellation_reason"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    index("subscriptions_customer_idx").on(t.customerId),
    index("subscriptions_next_billing_idx").on(t.status, t.nextBillingAt),
  ],
);

/**
 * Money in. `reference` is the provider's transaction id where there is one and is unique,
 * so replaying a webhook cannot record the same payment twice.
 */
export const payments = pgTable(
  "payments",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    customerId: uuid("customer_id")
      .notNull()
      .references(() => customers.id, { onDelete: "restrict" }),
    subscriptionId: uuid("subscription_id").references(() => subscriptions.id, {
      onDelete: "set null",
    }),
    kind: paymentKindEnum("kind").notNull(),
    status: paymentStatusEnum("status").notNull().default("due"),
    amountPence: pence("amount_pence").notNull(),
    currency: text("currency").notNull().default(CURRENCY),
    /** "cash", "bank_transfer", or a provider name once one is integrated. */
    method: text("method"),
    reference: text("reference"),
    dueAt: timestampTz("due_at"),
    paidAt: timestampTz("paid_at"),
    note: text("note"),
    createdAt: createdAt(),
    updatedAt: updatedAt(),
  },
  (t) => [
    index("payments_customer_idx").on(t.customerId, t.createdAt),
    index("payments_status_idx").on(t.status),
    uniqueIndex("payments_reference_uq").on(t.reference),
  ],
);
