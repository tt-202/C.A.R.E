export const MEAL_DONE_CHANNEL = "care-meal-finished";
export const MEAL_DONE_STORAGE_KEY = "care_meal_finished_ping";

export type MealDoneAlertPayload = {
  type: "meal_finished";
  finishedAtMs: number;
  careRecipientName: string;
  caregiverName: string;
  bitesTotal: number;
  plannedMealTime: string;
};

export function formatMealDoneNotification(alert: MealDoneAlertPayload): {
  title: string;
  body: string;
} {
  const name = alert.careRecipientName || "User";
  const title = `C.A.R.E — ${name} finished their meal`;
  const mealPart = alert.plannedMealTime ? ` (${alert.plannedMealTime})` : "";
  const bitePart =
    alert.bitesTotal > 0
      ? ` — ${alert.bitesTotal} bite${alert.bitesTotal === 1 ? "" : "s"} recorded`
      : "";
  const body = `${name} tapped Done${mealPart}${bitePart}.`;
  return { title, body };
}

/** Same-browser / same-device: caregiver tab hears this immediately (no 15s poll wait). */
export function broadcastMealFinishedLocally(alert: MealDoneAlertPayload): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(MEAL_DONE_STORAGE_KEY, JSON.stringify(alert));
    window.dispatchEvent(new CustomEvent("care-meal-finished", { detail: alert }));
  } catch {
    /* ignore */
  }
  try {
    if (typeof BroadcastChannel !== "undefined") {
      new BroadcastChannel(MEAL_DONE_CHANNEL).postMessage(alert);
    }
  } catch {
    /* ignore */
  }
}

export function parseMealDoneAlert(data: unknown): MealDoneAlertPayload | null {
  if (!data || typeof data !== "object") return null;
  const row = data as Record<string, unknown>;
  if (row.type !== "meal_finished" || typeof row.finishedAtMs !== "number") return null;
  return {
    type: "meal_finished",
    finishedAtMs: row.finishedAtMs,
    careRecipientName: typeof row.careRecipientName === "string" ? row.careRecipientName : "",
    caregiverName: typeof row.caregiverName === "string" ? row.caregiverName : "",
    bitesTotal: typeof row.bitesTotal === "number" ? row.bitesTotal : 0,
    plannedMealTime: typeof row.plannedMealTime === "string" ? row.plannedMealTime : "",
  };
}
