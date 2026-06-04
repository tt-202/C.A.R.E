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

function pairLatestAlertRef(carePairId: string) {
  return getFirebaseAdminFirestore()
    .collection("carePairs")
    .doc(carePairId)
    .collection("careAlerts")
    .doc("latest");
}

/** Legacy path kept for older deployments during transition. */
function legacyLatestAlertRef(firebaseUid: string) {
  return getFirebaseAdminFirestore()
    .collection("users")
    .doc(firebaseUid)
    .collection("careAlerts")
    .doc("latest");
}

export async function publishMealFinishedAlert(
  carePairId: string,
  data: Omit<MealFinishedAlert, "type" | "finishedAtMs">,
): Promise<MealFinishedAlert> {
  const finishedAtMs = Date.now();
  const alert: MealFinishedAlert = {
    type: "meal_finished",
    finishedAtMs,
    ...data,
  };
  await pairLatestAlertRef(carePairId).set({
    ...alert,
    updatedAt: FieldValue.serverTimestamp(),
  });
  return alert;
}

export async function getLatestMealFinishedAlert(carePairId: string): Promise<MealFinishedAlert | null> {
  const snap = await pairLatestAlertRef(carePairId).get();
  if (snap.exists) {
    return parseAlertDoc(snap.data());
  }

  const legacy = await legacyLatestAlertRef(carePairId).get();
  if (!legacy.exists) return null;
  return parseAlertDoc(legacy.data());
}

function parseAlertDoc(data: FirebaseFirestore.DocumentData | undefined): MealFinishedAlert | null {
  if (!data) return null;
  const partial = data as Partial<MealFinishedAlert>;
  if (partial.type !== "meal_finished" || typeof partial.finishedAtMs !== "number") {
    return null;
  }
  return {
    type: "meal_finished",
    finishedAtMs: partial.finishedAtMs,
    careRecipientName: partial.careRecipientName ?? "",
    caregiverName: partial.caregiverName ?? "",
    bitesTotal: partial.bitesTotal ?? 0,
    plannedMealTime: partial.plannedMealTime ?? "",
  };
}
