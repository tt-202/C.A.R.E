"use client";

import { useEffect, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { getClientDb, isFirebaseConfigured } from "@/lib/firebaseClient";
import {
  type RobotButtonInput,
  type RobotFeedCounts,
  type RobotLiveStatus,
  robotButtonInputPath,
  robotFeedCountsPath,
  robotLiveStatusPath,
} from "@/lib/robotFirestorePaths";

type Options = {
  robotId: string;
  enabled: boolean;
};

const empty = {
  live: null,
  feedCounts: null,
  buttonInput: null,
  error: null,
} as const;

export function useRobotFirestore({ robotId, enabled }: Options) {
  const [live, setLive] = useState<RobotLiveStatus | null>(null);
  const [feedCounts, setFeedCounts] = useState<RobotFeedCounts | null>(null);
  const [buttonInput, setButtonInput] = useState<RobotButtonInput | null>(null);
  const [error, setError] = useState<string | null>(null);

  const listening = enabled && Boolean(robotId) && isFirebaseConfigured();

  useEffect(() => {
    if (!listening) return;

    const db = getClientDb();
    const refs = [
      doc(db, ...robotLiveStatusPath(robotId)),
      doc(db, ...robotFeedCountsPath(robotId)),
      doc(db, ...robotButtonInputPath(robotId)),
    ] as const;

    const unsubs = [
      onSnapshot(
        refs[0],
        (snap) => setLive(snap.exists() ? (snap.data() as RobotLiveStatus) : null),
        (err) => {
          console.warn("[robot live] listen failed", err);
          setError(err.message);
        },
      ),
      onSnapshot(
        refs[1],
        (snap) => setFeedCounts(snap.exists() ? (snap.data() as RobotFeedCounts) : null),
        (err) => console.warn("[robot feed_counts] listen failed", err),
      ),
      onSnapshot(
        refs[2],
        (snap) => setButtonInput(snap.exists() ? (snap.data() as RobotButtonInput) : null),
        (err) => console.warn("[robot button_input] listen failed", err),
      ),
    ];

    return () => {
      for (const unsub of unsubs) unsub();
    };
  }, [listening, robotId]);

  if (!listening) {
    return empty;
  }

  return { live, feedCounts, buttonInput, error };
}
