import { FieldValue } from "firebase-admin/firestore";
import { getFirebaseAdminFirestore } from "@/lib/firebaseAdmin";
import type { CareMemberRole } from "@/lib/carePair";

function memberRef(carePairId: string, firebaseUid: string) {
  return getFirebaseAdminFirestore()
    .collection("carePairs")
    .doc(carePairId)
    .collection("members")
    .doc(firebaseUid);
}

export async function syncCarePairMember(
  carePairId: string,
  firebaseUid: string,
  role: CareMemberRole,
): Promise<void> {
  await memberRef(carePairId, firebaseUid).set({
    role,
    updatedAt: FieldValue.serverTimestamp(),
  });
}

export async function removeCarePairMember(carePairId: string, firebaseUid: string): Promise<void> {
  await memberRef(carePairId, firebaseUid).delete();
}

export async function listCaregiverFirebaseUids(carePairId: string): Promise<string[]> {
  const snap = await getFirebaseAdminFirestore()
    .collection("carePairs")
    .doc(carePairId)
    .collection("members")
    .where("role", "==", "caregiver")
    .get();

  return snap.docs.map((doc) => doc.id);
}
