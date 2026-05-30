import { FieldValue, type Timestamp } from "firebase-admin/firestore";
import { getFirebaseAdminFirestore } from "@/lib/firebaseAdmin";
import type { RobotCommandPayload, RobotCommandStatus, RobotCommandType } from "@/lib/robot";
import { getRobotId } from "@/lib/robot";

export type RobotCommandDoc = {
  cmd: RobotCommandType;
  status: RobotCommandStatus;
  userId: string;
  payload: RobotCommandPayload | null;
  error: string | null;
  createdAt: Timestamp;
  updatedAt: Timestamp;
};

function commandsCollection(robotId: string) {
  return getFirebaseAdminFirestore()
    .collection("robots")
    .doc(robotId)
    .collection("commands");
}

export async function enqueueRobotCommand(
  userId: string,
  cmd: RobotCommandType,
  payload?: RobotCommandPayload,
): Promise<{ commandId: string; robotId: string }> {
  const robotId = getRobotId();
  const ref = commandsCollection(robotId).doc();
  await ref.set({
    cmd,
    status: "pending",
    userId,
    payload: payload ?? null,
    error: null,
    createdAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
  });
  return { commandId: ref.id, robotId };
}

export async function getRobotCommand(
  robotId: string,
  commandId: string,
): Promise<(RobotCommandDoc & { commandId: string }) | null> {
  const snap = await commandsCollection(robotId).doc(commandId).get();
  if (!snap.exists) return null;
  const data = snap.data() as RobotCommandDoc;
  return { ...data, commandId: snap.id };
}
