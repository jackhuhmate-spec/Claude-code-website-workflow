/**
 * The functions that produce the `*_normalised` columns.
 *
 * They live in this package rather than in a caller because the columns and their
 * comparison rules are one decision. A lead importer and a discovery agent that normalised
 * differently would each believe their own dedupe key was correct while quietly writing
 * duplicates — and for `suppressions.value_normalised`, a mismatch means emailing someone
 * who has opted out.
 */

/**
 * Comparison key for an email address.
 *
 * Case is folded because the local part is case-insensitive in every provider that matters
 * here, and treating `Info@` and `info@` as different addresses would let a suppression be
 * bypassed by capitalisation. Nothing else is altered: stripping dots or `+tags` would
 * merge genuinely distinct mailboxes on some providers.
 */
export function normaliseEmail(value: string): string {
  return value.trim().toLowerCase();
}

/**
 * Comparison key for a UK phone number: digits only, in national form.
 *
 * `020 8166 9967`, `+44 20 8166 9967` and `02081669967` are one number, and a suppression
 * on any of them must match all three.
 */
export function normalisePhone(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.startsWith("44") && digits.length > 10) {
    return `0${digits.slice(2)}`;
  }
  return digits;
}

/**
 * Comparison key for a business name: lower-cased, punctuation removed, spaces collapsed.
 *
 * Legal suffixes are deliberately kept. "Smith Roofing" and "Smith Roofing Ltd" may well be
 * the same firm, but they may equally be two, and merging them loses a real business with
 * no way to recover it — the safe error here is a duplicate a human can spot, not a
 * silent deletion.
 */
export function normaliseName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Registrable host of a URL, without `www.`, for spotting two listings of one business.
 * Returns null for anything unparseable rather than guessing.
 */
export function normaliseHost(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") {
    return null;
  }
  const withScheme = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  try {
    return new URL(withScheme).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return null;
  }
}
