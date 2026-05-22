import {
  broadcastMealFinishedLocally,
  type MealDoneAlertPayload,
} from "@/lib/mealDoneAlert";

export type MealFinishedNotifyPayload = {
  careRecipientName: string;
  caregiverName: string;
  bitesTotal: number;
  plannedMealTime: string;
};

export type NotifyCaregiverResult =
  | { ok: true; alert: MealDoneAlertPayload }
  | { ok: false; error: string };

/** Called from the User role when they tap Done — stores an alert the Caregiver device can receive. */
export async function notifyCaregiverMealFinished(
  getIdToken: () => Promise<string>,
  payload: MealFinishedNotifyPayload,
): Promise<NotifyCaregiverResult> {
  try {
    const token = await getIdToken();
    const res = await fetch("/api/alerts/meal-finished", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const body = (await res.json().catch(() => ({}))) as {
      error?: string;
      alert?: MealDoneAlertPayload;
    };
    if (!res.ok) {
      const error = body.error?.trim() || `Server error (${res.status})`;
      console.warn("[caregiver alert] publish failed", res.status, error);
      return { ok: false, error };
    }
    if (body.alert) {
      broadcastMealFinishedLocally(body.alert);
      return { ok: true, alert: body.alert };
    }
    return { ok: false, error: "No alert returned from server" };
  } catch (e) {
    const error = e instanceof Error ? e.message : "Network error";
    console.warn("[caregiver alert] publish failed", e);
    return { ok: false, error };
  }
}
