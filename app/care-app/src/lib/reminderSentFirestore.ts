import { FieldValue } from "firebase-admin/firestore";
import { getFirebaseAdminFirestore } from "@/lib/firebaseAdmin";

function sentRef(userId: string, fireKey: string) {
  return getFirebaseAdminFirestore()
    .collection("users")
    .doc(userId)
    .collection("reminderSent")
    .doc(fireKey);
}

export async function wasReminderSent(userId: string, fireKey: string): Promise<boolean> {
  const snap = await sentRef(userId, fireKey).get();
  return snap.exists;
}

export async function markReminderSent(userId: string, fireKey: string): Promise<void> {
  await sentRef(userId, fireKey).set({ sentAt: FieldValue.serverTimestamp() });
}
