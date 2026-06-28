"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { getClientDb, isFirebaseConfigured } from "@/lib/firebaseClient";
import { refreshRobotLiveStatus } from "@/lib/robotClient";
import {
  type RobotButtonInput,
  type RobotFeedCounts,
  type RobotLiveStatus,
  robotButtonInputPath,
  robotFeedCountsPath,
  robotLiveStatusPath,
} from "@/lib/robotFirestorePaths";
import { isJetsonEffectivelyOnline } from "@/lib/robotStatusDisplay";

type Options = {
  robotId: string;
  enabled: boolean;
  getIdToken?: () => Promise<string>;
};

const noopRefresh = async () => {};

const empty = {
  live: null,
  feedCounts: null,
  buttonInput: null,
  error: null,
  refresh: noopRefresh,
  refreshing: false,
  lastRefreshedAt: null,
  statusStale: false,
  clearedStaleOnRefresh: false,
  clearedHistoryOnRefresh: false,
} as const;

export function useRobotFirestore({ robotId, enabled, getIdToken }: Options) {
  const [live, setLive] = useState<RobotLiveStatus | null>(null);
  const [feedCounts, setFeedCounts] = useState<RobotFeedCounts | null>(null);
  const [buttonInput, setButtonInput] = useState<RobotButtonInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [statusStale, setStatusStale] = useState(false);
  const [clearedStaleOnRefresh, setClearedStaleOnRefresh] = useState(false);
  const [clearedHistoryOnRefresh, setClearedHistoryOnRefresh] = useState(false);
  const pauseListenerRef = useRef(false);
  const autoStaleClearRef = useRef(false);

  const listening = enabled && Boolean(robotId) && isFirebaseConfigured();

  const applySnapshot = useCallback(
    (snapshot: {
      live: RobotLiveStatus | null;
      feedCounts: RobotFeedCounts | null;
      buttonInput: RobotButtonInput | null;
      stale?: boolean;
      clearedStale?: boolean;
      clearedHistory?: boolean;
    }) => {
      setLive(snapshot.live);
      setFeedCounts(snapshot.feedCounts);
      setButtonInput(snapshot.buttonInput);
      setStatusStale(Boolean(snapshot.stale));
      setClearedStaleOnRefresh(Boolean(snapshot.clearedStale));
      setClearedHistoryOnRefresh(Boolean(snapshot.clearedHistory));
    },
    [],
  );

  const refresh = useCallback(
    async (opts?: { clearHistory?: boolean }) => {
      if (!robotId) return;

      pauseListenerRef.current = true;
      setRefreshing(true);
      setError(null);
      setClearedStaleOnRefresh(false);
      setClearedHistoryOnRefresh(false);
      applySnapshot({
        live: null,
        feedCounts: null,
        buttonInput: null,
        stale: false,
        clearedStale: false,
        clearedHistory: false,
      });

      try {
        if (getIdToken) {
          const snapshot = await refreshRobotLiveStatus(getIdToken, robotId, {
            clearHistory: opts?.clearHistory !== false,
          });
          applySnapshot({
            live: snapshot.live,
            feedCounts: snapshot.feedCounts,
            buttonInput: snapshot.buttonInput,
            stale: snapshot.stale,
            clearedStale: snapshot.clearedStale,
            clearedHistory: snapshot.clearedHistory,
          });
        } else if (isFirebaseConfigured()) {
          throw new Error("Sign in required to refresh robot status.");
        } else {
          throw new Error("Firebase is not configured.");
        }
        setLastRefreshedAt(new Date());
      } catch (err) {
        const message = err instanceof Error ? err.message : "Refresh failed";
        console.warn("[robot] manual refresh failed", err);
        setError(message);
      } finally {
        pauseListenerRef.current = false;
        setRefreshing(false);
      }
    },
    [applySnapshot, getIdToken, robotId],
  );

  useEffect(() => {
    if (!listening || !getIdToken || refreshing) return;
    if (!statusStale || autoStaleClearRef.current) return;
    autoStaleClearRef.current = true;
    void refresh({ clearHistory: false });
  }, [getIdToken, listening, refresh, refreshing, statusStale]);

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
        (snap) => {
          if (pauseListenerRef.current) return;
          const nextLive = snap.exists() ? (snap.data() as RobotLiveStatus) : null;
          setLive(nextLive);
          setStatusStale(!isJetsonEffectivelyOnline(nextLive));
        },
        (err) => {
          console.warn("[robot live] listen failed", err);
          setError(err.message);
        },
      ),
      onSnapshot(
        refs[1],
        (snap) => {
          if (pauseListenerRef.current) return;
          setFeedCounts(snap.exists() ? (snap.data() as RobotFeedCounts) : null);
        },
        (err) => console.warn("[robot feed_counts] listen failed", err),
      ),
      onSnapshot(
        refs[2],
        (snap) => {
          if (pauseListenerRef.current) return;
          setButtonInput(snap.exists() ? (snap.data() as RobotButtonInput) : null);
        },
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

  return {
    live,
    feedCounts,
    buttonInput,
    error,
    refresh,
    refreshing,
    lastRefreshedAt,
    statusStale,
    clearedStaleOnRefresh,
    clearedHistoryOnRefresh,
  };
}
