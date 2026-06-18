import {
  getLatestCareAlert,
  publishMealEmergencyAlert,
  publishMealFinishedAlert,
  type CareAlert,
} from "@/lib/careAlertsFirestore";
import {
  formatMealDoneNotification,
  formatMealEmergencyNotification,
} from "@/lib/mealDoneAlert";
import { listCaregiverFirebaseUidsForPair } from "@/lib/carePair";
import { sendPushToUsers } from "@/lib/fcmSend";

export type CaregiverMealAlertInput = {
  carePairId: string;
  careRecipientName: string;
  caregiverName: string;
  bitesTotal: number;
  plannedMealTime: string;
  emergency: boolean;
};

/** Write Firestore alert + FCM push to all caregivers on the pair. */
export async function publishAndPushCaregiverMealAlert(
  input: CaregiverMealAlertInput,
): Promise<CareAlert> {
  const base = {
    careRecipientName: input.careRecipientName,
    caregiverName: input.caregiverName,
    bitesTotal: input.bitesTotal,
    plannedMealTime: input.plannedMealTime,
  };

  const alert = input.emergency
    ? await publishMealEmergencyAlert(input.carePairId, base)
    : await publishMealFinishedAlert(input.carePairId, base);

  const { title, body } =
    alert.type === "meal_emergency"
      ? formatMealEmergencyNotification(alert)
      : formatMealDoneNotification(alert);

  const caregiverUids = await listCaregiverFirebaseUidsForPair(input.carePairId);
  await sendPushToUsers(caregiverUids, {
    title,
    body,
    tag: `${alert.type}-${alert.finishedAtMs}`,
    alertType: alert.type,
  });

  return alert;
}

/** Prevent stale clients from overwriting a fresh emergency with meal-finished. */
export async function shouldSkipMealFinishedPublish(carePairId: string): Promise<boolean> {
  const latest = await getLatestCareAlert(carePairId);
  if (latest?.type !== "meal_emergency") return false;
  return Date.now() - latest.finishedAtMs < 120_000;
}
