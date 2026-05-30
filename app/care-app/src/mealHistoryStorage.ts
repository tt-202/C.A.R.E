export type MealHistoryEntry = {
  id: string;
  /** When the meal was finished (ISO). */
  endedAt: string;
  /** Wall-clock time from first Start to Stop / complete / emergency (ms). */
  durationMs: number;
  bitesTotal: number;
  /** Bites recorded per plate section 1–4. */
  bySection: Record<1 | 2 | 3 | 4, number>;
  /** Planned meal time from the form (HH:MM), if any. */
  plannedMealTime?: string;
};

function storageKey(userEmail: string) {
  return `care-meal-history-${encodeURIComponent(userEmail.toLowerCase().trim())}`;
}

export function loadMealHistory(userEmail: string): MealHistoryEntry[] {
  if (!userEmail) return [];
  try {
    const raw = localStorage.getItem(storageKey(userEmail));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isValidEntry);
  } catch {
    return [];
  }
}

function isValidEntry(x: unknown): x is MealHistoryEntry {
  if (x === null || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    typeof o.endedAt === "string" &&
    typeof o.durationMs === "number" &&
    typeof o.bitesTotal === "number" &&
    typeof o.bySection === "object" &&
    o.bySection !== null
  );
}

export function saveMealHistory(userEmail: string, entries: MealHistoryEntry[]) {
  if (!userEmail) return;
  try {
    localStorage.setItem(storageKey(userEmail), JSON.stringify(entries));
  } catch {
    /* ignore quota */
  }
}

export function formatDuration(ms: number): string {
  if (ms < 0) ms = 0;
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  if (m === 0) return `${s} sec`;
  return `${m} min ${s} sec`;
}
