/** Bite hold at mouth — seconds the arm stays still before returning home. */

export const DEFAULT_BITE_HOLD_SECONDS = 2;
export const MIN_BITE_HOLD_SECONDS = 1;
export const MAX_BITE_HOLD_SECONDS = 10;

export function normalizeBiteHoldSeconds(value: unknown): number {
  const n = typeof value === "number" ? value : Number.parseFloat(String(value ?? ""));
  if (!Number.isFinite(n)) return DEFAULT_BITE_HOLD_SECONDS;
  return Math.min(MAX_BITE_HOLD_SECONDS, Math.max(MIN_BITE_HOLD_SECONDS, Math.round(n * 10) / 10));
}
