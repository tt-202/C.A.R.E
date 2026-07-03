const STORAGE_PREFIX = "care_meal_reminder_sent_";

/** Client-side dedup: one in-app banner per meal slot per day (no FCM path). */
export function wasMealReminderShownLocally(fireKey: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(`${STORAGE_PREFIX}${fireKey}`) === "1";
  } catch {
    return false;
  }
}

export function markMealReminderShownLocally(fireKey: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${fireKey}`, "1");
  } catch {
    /* ignore */
  }
}
