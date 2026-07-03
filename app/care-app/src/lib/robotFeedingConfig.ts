import { FieldValue } from "firebase-admin/firestore";
import { getFirebaseAdminFirestore } from "@/lib/firebaseAdmin";
import { getRobotId } from "@/lib/robot";
import { normalizeBiteHoldSeconds } from "@/lib/biteHoldConfig";

/** Push bite-hold setting to Firestore for the Jetson worker (robots/{id}/config/feeding). */
export async function syncRobotFeedingConfig(biteHoldSeconds: unknown): Promise<number> {
  const seconds = normalizeBiteHoldSeconds(biteHoldSeconds);
  const robotId = getRobotId();
  await getFirebaseAdminFirestore()
    .collection("robots")
    .doc(robotId)
    .collection("config")
    .doc("feeding")
    .set(
      {
        bite_hold_seconds: seconds,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    );
  return seconds;
}
