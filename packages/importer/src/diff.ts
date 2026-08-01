/**
 * The fields of `next` that actually differ from `current`.
 *
 * The importer writes an UPDATE only when this returns something, which is what makes a
 * second run provably a no-op rather than merely harmless — "unchanged" becomes an
 * observable count instead of a claim. It also keeps `updated_at` honest, so that column
 * means "when the data last changed" rather than "when the import last ran".
 *
 * A key whose value in `next` is `undefined` is left alone. That distinction matters: the
 * CSVs frequently have nothing to say about a column, and treating silence as `null` would
 * erase data every run.
 */
export function changedFields<T extends object>(
  current: T,
  next: Partial<T>,
): Partial<T> {
  const changes: Partial<T> = {};

  for (const key of Object.keys(next) as (keyof T)[]) {
    const proposed = next[key];
    if (proposed === undefined) {
      continue;
    }
    if (!isEqual(current[key], proposed)) {
      changes[key] = proposed;
    }
  }

  return changes;
}

export function hasChanges(changes: object): boolean {
  return Object.keys(changes).length > 0;
}

function isEqual(a: unknown, b: unknown): boolean {
  if (a instanceof Date && b instanceof Date) {
    return a.getTime() === b.getTime();
  }
  return Object.is(a, b);
}
