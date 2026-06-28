import { FieldValue, type DocumentData } from "firebase-admin/firestore";
import { getFirebaseAdminFirestore } from "@/lib/firebaseAdmin";
import { getRobotId } from "@/lib/robot";
import {
  type RobotButtonInput,
  type RobotFeedCounts,
  type RobotLiveStatus,
} from "@/lib/robotFirestorePaths";
import type { RobotFirestoreSnapshot } from "@/lib/robotStatusTypes";
import { isJetsonEffectivelyOnline } from "@/lib/robotStatusDisplay";

export type { RobotFirestoreSnapshot } from "@/lib/robotStatusTypes";

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

function feedCountsRef(robotId: string) {
  return getFirebaseAdminFirestore()
    .collection("robots")
    .doc(robotId)
    .collection("stats")
    .doc("feed_counts");
}

function asLive(data: DocumentData | undefined): RobotLiveStatus | null {
  return data ? (data as RobotLiveStatus) : null;
}

function asFeedCounts(data: DocumentData | undefined): RobotFeedCounts | null {
  return data ? (data as RobotFeedCounts) : null;
}

function asButtonInput(data: DocumentData | undefined): RobotButtonInput | null {
  return data ? (data as RobotButtonInput) : null;
}

export async function readRobotFirestoreStatus(robotId?: string): Promise<RobotFirestoreSnapshot> {
  const rid = robotId?.trim() || getRobotId();
  const [liveSnap, feedSnap, buttonSnap] = await Promise.all([
    liveRef(rid).get(),
    feedCountsRef(rid).get(),
    buttonInputRef(rid).get(),
  ]);
  const live = asLive(liveSnap.exists ? liveSnap.data() : undefined);
  const stale = !isJetsonEffectivelyOnline(live);
  return {
    robotId: rid,
    live,
    feedCounts: asFeedCounts(feedSnap.exists ? feedSnap.data() : undefined),
    buttonInput: asButtonInput(buttonSnap.exists ? buttonSnap.data() : undefined),
    fetchedAt: new Date().toISOString(),
    stale,
    clearedStale: false,
    clearedHistory: false,
  };
}

/** Reset lifetime feed stats and button press counters in Firestore. */
export async function clearRobotHistoryStats(robotId?: string): Promise<void> {
  const rid = robotId?.trim() || getRobotId();
  await feedCountsRef(rid).set(
    {
      total_bites: 0,
      successful_feeds: 0,
      failed_feeds: 0,
      total_feed_attempts: 0,
      eat_press_count: 0,
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true },
  );
  await buttonInputRef(rid).set(
    {
      eat_pressed: false,
      stop_pressed: false,
      eat_press_seq: 0,
      last_pin: FieldValue.delete(),
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true },
  );
}

export type RefreshRobotStatusOptions = {
  robotId?: string;
  /** When true, zero lifetime stats and button counters (caregiver Refresh button). */
  clearHistory?: boolean;
};

/** Force-fetch from Firestore; optionally reset session and clear all counters. */
export async function refreshRobotLiveStatus(
  opts?: RefreshRobotStatusOptions,
): Promise<RobotFirestoreSnapshot> {
  const rid = opts?.robotId?.trim() || getRobotId();
  const clearHistory = Boolean(opts?.clearHistory);
  const initial = await readRobotFirestoreStatus(rid);
  const shouldResetSession = clearHistory || initial.stale;

  if (!shouldResetSession) {
    return initial;
  }

  await resetRobotMealSession({
    robotId: rid,
    emergency: false,
    jetsonOnline: clearHistory ? false : !initial.stale,
  });

  if (clearHistory) {
    await clearRobotHistoryStats(rid);
  }

  const refreshed = await readRobotFirestoreStatus(rid);
  return {
    ...refreshed,
    stale: clearHistory ? refreshed.stale : initial.stale,
    clearedStale: shouldResetSession,
    clearedHistory: clearHistory,
  };
}

/** Reset in-meal bite count and state after Done / Emergency stop (lifetime stats unchanged). */
export async function resetRobotMealSession(opts?: {
  robotId?: string;
  emergency?: boolean;
  jetsonOnline?: boolean;
}): Promise<void> {
  const robotId = opts?.robotId?.trim() || getRobotId();
  const jetsonOnline = opts?.jetsonOnline ?? true;
  await liveRef(robotId).set(
    {
      state: "IDLE",
      bite_count: 0,
      section: 1,
      emergency: Boolean(opts?.emergency),
      jetson_online: jetsonOnline,
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
