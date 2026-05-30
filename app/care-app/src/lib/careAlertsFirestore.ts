import { FieldValue } from "firebase-admin/firestore";
import { getFirebaseAdminFirestore } from "@/lib/firebaseAdmin";

export type MealFinishedAlert = {
  type: "meal_finished";
  finishedAtMs: number;
  careRecipientName: string;
  caregiverName: string;
  bitesTotal: number;
  plannedMealTime: string;
};

function latestAlertRef(userId: string) {
  return getFirebaseAdminFirestore()
    .collection("users")
    .doc(userId)
    .collection("careAlerts")
    .doc("latest");
}

export async function publishMealFinishedAlert(
  userId: string,
  data: Omit<MealFinishedAlert, "type" | "finishedAtMs">,
): Promise<MealFinishedAlert> {
  const finishedAtMs = Date.now();
  const alert: MealFinishedAlert = {
    type: "meal_finished",
    finishedAtMs,
    ...data,
  };
  await latestAlertRef(userId).set({
    ...alert,
    updatedAt: FieldValue.serverTimestamp(),
  });
  return alert;
}

export async function getLatestMealFinishedAlert(userId: string): Promise<MealFinishedAlert | null> {
  const snap = await latestAlertRef(userId).get();
  if (!snap.exists) return null;
  const data = snap.data() as Partial<MealFinishedAlert>;
  if (data.type !== "meal_finished" || typeof data.finishedAtMs !== "number") {
    return null;
  }
  return {
    type: "meal_finished",
    finishedAtMs: data.finishedAtMs,
    careRecipientName: data.careRecipientName ?? "",
    caregiverName: data.caregiverName ?? "",
    bitesTotal: data.bitesTotal ?? 0,
    plannedMealTime: data.plannedMealTime ?? "",
  };
}
