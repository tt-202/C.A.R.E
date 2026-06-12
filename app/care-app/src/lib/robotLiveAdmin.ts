import { FieldValue } from "firebase-admin/firestore";
import { getFirebaseAdminFirestore } from "@/lib/firebaseAdmin";
import { getRobotId } from "@/lib/robot";

function liveRef(robotId: string) {
  return getFirebaseAdminFirestore()
    .collection("robots")
    .doc(robotId)
    .collection("status")
    .doc("live");
}

function buttonInputRef(robotId: string) {
  return getFirebaseAdminFirestore()
    .collection("robots")
    .doc(robotId)
    .collection("status")
    .doc("button_input");
}

/** Reset in-meal bite count and state after Done / Emergency stop (lifetime stats unchanged). */
export async function resetRobotMealSession(opts?: {
  robotId?: string;
  emergency?: boolean;
}): Promise<void> {
  const robotId = opts?.robotId?.trim() || getRobotId();
  await liveRef(robotId).set(
    {
      state: "IDLE",
      bite_count: 0,
      section: 1,
      emergency: Boolean(opts?.emergency),
      jetson_online: true,
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true },
  );
  await buttonInputRef(robotId).set(
    {
      eat_pressed: false,
      stop_pressed: Boolean(opts?.emergency),
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true },
  );
}

/** Start a new meal session on the robot status doc. */
export async function startRobotMealSession(opts?: { robotId?: string; section?: number }): Promise<void> {
  const robotId = opts?.robotId?.trim() || getRobotId();
  await liveRef(robotId).set(
    {
      state: "FEEDING",
      bite_count: 0,
      section: opts?.section ?? 1,
      emergency: false,
      jetson_online: true,
      meal_started_at: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true },
  );
}
