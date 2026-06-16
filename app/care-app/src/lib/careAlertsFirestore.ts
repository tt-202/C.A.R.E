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

export type MealEmergencyAlert = {
  type: "meal_emergency";
  finishedAtMs: number;
  careRecipientName: string;
  caregiverName: string;
  bitesTotal: number;
  plannedMealTime: string;
};

export type CareAlert = MealFinishedAlert | MealEmergencyAlert;

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

async function publishCareAlert(carePairId: string, alert: CareAlert): Promise<CareAlert> {
  await pairLatestAlertRef(carePairId).set({
    ...alert,
    updatedAt: FieldValue.serverTimestamp(),
  });
  return alert;
}

export async function publishMealFinishedAlert(
  carePairId: string,
  data: Omit<MealFinishedAlert, "type" | "finishedAtMs">,
): Promise<MealFinishedAlert> {
  const alert: MealFinishedAlert = {
    type: "meal_finished",
    finishedAtMs: Date.now(),
    ...data,
  };
  return publishCareAlert(carePairId, alert) as Promise<MealFinishedAlert>;
}

export async function publishMealEmergencyAlert(
  carePairId: string,
  data: Omit<MealEmergencyAlert, "type" | "finishedAtMs">,
): Promise<MealEmergencyAlert> {
  const alert: MealEmergencyAlert = {
    type: "meal_emergency",
    finishedAtMs: Date.now(),
    ...data,
  };
  return publishCareAlert(carePairId, alert) as Promise<MealEmergencyAlert>;
}

export async function getLatestCareAlert(carePairId: string): Promise<CareAlert | null> {
  const snap = await pairLatestAlertRef(carePairId).get();
  if (snap.exists) {
    return parseAlertDoc(snap.data());
  }

  const legacy = await legacyLatestAlertRef(carePairId).get();
  if (!legacy.exists) return null;
  return parseAlertDoc(legacy.data());
}

/** @deprecated use getLatestCareAlert */
export async function getLatestMealFinishedAlert(carePairId: string): Promise<MealFinishedAlert | null> {
  const latest = await getLatestCareAlert(carePairId);
  return latest?.type === "meal_finished" ? latest : null;
}

function parseAlertDoc(data: FirebaseFirestore.DocumentData | undefined): CareAlert | null {
  if (!data) return null;
  const partial = data as Partial<CareAlert>;
  if (typeof partial.finishedAtMs !== "number") return null;

  if (partial.type === "meal_emergency") {
    return {
      type: "meal_emergency",
      finishedAtMs: partial.finishedAtMs,
      careRecipientName: partial.careRecipientName ?? "",
      caregiverName: partial.caregiverName ?? "",
      bitesTotal: partial.bitesTotal ?? 0,
      plannedMealTime: partial.plannedMealTime ?? "",
    };
  }

  if (partial.type !== "meal_finished") return null;
  return {
    type: "meal_finished",
    finishedAtMs: partial.finishedAtMs,
    careRecipientName: partial.careRecipientName ?? "",
    caregiverName: partial.caregiverName ?? "",
    bitesTotal: partial.bitesTotal ?? 0,
    plannedMealTime: partial.plannedMealTime ?? "",
  };
}
