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

export type MealEmergencyAlertPayload = {
  type: "meal_emergency";
  finishedAtMs: number;
  careRecipientName: string;
  caregiverName: string;
  bitesTotal: number;
  plannedMealTime: string;
};

export type PlateEmptyAlertPayload = {
  type: "plate_empty";
  finishedAtMs: number;
  careRecipientName: string;
  caregiverName: string;
  robotId: string;
  section: number;
  plateStatus: string;
};

export type CareAlertPayload = MealDoneAlertPayload | MealEmergencyAlertPayload | PlateEmptyAlertPayload;

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

export function formatMealEmergencyNotification(alert: MealEmergencyAlertPayload): {
  title: string;
  body: string;
} {
  const name = alert.careRecipientName || "User";
  const title = `C.A.R.E — Emergency: ${name} needs help`;
  const mealPart = alert.plannedMealTime ? ` during ${alert.plannedMealTime}` : "";
  const bitePart =
    alert.bitesTotal > 0
      ? ` ${alert.bitesTotal} bite${alert.bitesTotal === 1 ? "" : "s"} were recorded before the stop.`
      : "";
  const body = `${name} pressed Emergency stop${mealPart}.${bitePart} Please check on them.`.trim();
  return { title, body };
}

export function formatPlateEmptyNotification(alert: PlateEmptyAlertPayload): {
  title: string;
  body: string;
} {
  const name = alert.careRecipientName || "User";
  const title = `C.A.R.E — Plate empty (${name})`;
  const sectionPart =
    alert.section >= 1 && alert.section <= 4 ? ` Section ${alert.section} selected.` : "";
  const body = `YOLO detected an empty plate for ${name}.${sectionPart} Please refill the plate.`;
  return { title, body };
}

export function formatCareAlertNotification(alert: CareAlertPayload): { title: string; body: string } {
  if (alert.type === "meal_emergency") {
    return formatMealEmergencyNotification(alert);
  }
  if (alert.type === "plate_empty") {
    return formatPlateEmptyNotification(alert);
  }
  return formatMealDoneNotification(alert);
}

export function careAlertNotificationTag(alert: CareAlertPayload): string {
  return `${alert.type}-${alert.finishedAtMs}`;
}

/** Same-browser / same-device: caregiver tab hears this immediately (no poll wait). */
export function broadcastCareAlertLocally(alert: CareAlertPayload): void {
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

/** @deprecated use broadcastCareAlertLocally */
export function broadcastMealFinishedLocally(alert: MealDoneAlertPayload): void {
  broadcastCareAlertLocally(alert);
}

export function parseMealEmergencyAlert(data: unknown): MealEmergencyAlertPayload | null {
  if (!data || typeof data !== "object") return null;
  const row = data as Record<string, unknown>;
  if (row.type !== "meal_emergency" || typeof row.finishedAtMs !== "number") return null;
  return {
    type: "meal_emergency",
    finishedAtMs: row.finishedAtMs,
    careRecipientName: typeof row.careRecipientName === "string" ? row.careRecipientName : "",
    caregiverName: typeof row.caregiverName === "string" ? row.caregiverName : "",
    bitesTotal: typeof row.bitesTotal === "number" ? row.bitesTotal : 0,
    plannedMealTime: typeof row.plannedMealTime === "string" ? row.plannedMealTime : "",
  };
}

export function parsePlateEmptyAlert(data: unknown): PlateEmptyAlertPayload | null {
  if (!data || typeof data !== "object") return null;
  const row = data as Record<string, unknown>;
  if (row.type !== "plate_empty" || typeof row.finishedAtMs !== "number") return null;
  return {
    type: "plate_empty",
    finishedAtMs: row.finishedAtMs,
    careRecipientName: typeof row.careRecipientName === "string" ? row.careRecipientName : "",
    caregiverName: typeof row.caregiverName === "string" ? row.caregiverName : "",
    robotId: typeof row.robotId === "string" ? row.robotId : "",
    section: typeof row.section === "number" ? row.section : 0,
    plateStatus: typeof row.plateStatus === "string" ? row.plateStatus : "empty",
  };
}

export function parseCareAlert(data: unknown): CareAlertPayload | null {
  return parseMealDoneAlert(data) ?? parseMealEmergencyAlert(data) ?? parsePlateEmptyAlert(data);
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
