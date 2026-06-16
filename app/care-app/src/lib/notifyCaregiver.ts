import {
  broadcastCareAlertLocally,
  type CareAlertPayload,
  type MealDoneAlertPayload,
  type MealEmergencyAlertPayload,
} from "@/lib/mealDoneAlert";

export type MealFinishedNotifyPayload = {
  careRecipientName: string;
  caregiverName: string;
  bitesTotal: number;
  plannedMealTime: string;
};

export type NotifyCaregiverResult =
  | { ok: true; alert: CareAlertPayload }
  | { ok: false; error: string };

async function postCareAlert(
  getIdToken: () => Promise<string>,
  path: string,
  payload: MealFinishedNotifyPayload,
): Promise<NotifyCaregiverResult> {
  try {
    const token = await getIdToken();
    const res = await fetch(path, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const body = (await res.json().catch(() => ({}))) as {
      error?: string;
      alert?: CareAlertPayload;
    };
    if (!res.ok) {
      const error = body.error?.trim() || `Server error (${res.status})`;
      console.warn("[caregiver alert] publish failed", res.status, error);
      return { ok: false, error };
    }
    if (body.alert) {
      broadcastCareAlertLocally(body.alert);
      return { ok: true, alert: body.alert };
    }
    return { ok: false, error: "No alert returned from server" };
  } catch (e) {
    const error = e instanceof Error ? e.message : "Network error";
    console.warn("[caregiver alert] publish failed", e);
    return { ok: false, error };
  }
}

/** User tapped Done — meal completed normally. */
export async function notifyCaregiverMealFinished(
  getIdToken: () => Promise<string>,
  payload: MealFinishedNotifyPayload,
): Promise<NotifyCaregiverResult> {
  return postCareAlert(getIdToken, "/api/alerts/meal-finished", payload);
}

/** User tapped Emergency — warn caregiver something is wrong. */
export async function notifyCaregiverMealEmergency(
  getIdToken: () => Promise<string>,
  payload: MealFinishedNotifyPayload,
): Promise<NotifyCaregiverResult> {
  return postCareAlert(getIdToken, "/api/alerts/meal-emergency", payload);
}

export type { MealDoneAlertPayload, MealEmergencyAlertPayload };
