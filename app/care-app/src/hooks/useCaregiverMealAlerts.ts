"use client";

import { useEffect, useRef } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { doc, onSnapshot } from "firebase/firestore";
import { getClientAuth, getClientFirestore, isFirebaseConfigured } from "@/lib/firebaseClient";
import {
  careAlertNotificationTag,
  formatCareAlertNotification,
  MEAL_DONE_CHANNEL,
  MEAL_DONE_STORAGE_KEY,
  parseCareAlert,
  type CareAlertPayload,
} from "@/lib/mealDoneAlert";
import { showBrowserNotification } from "@/hooks/useMealReminders";

const POLL_MS = 4_000;
const SEEN_KEY_PREFIX = "care_meal_finished_seen_";

export type CaregiverMealAlertPayload = {
  title: string;
  body: string;
  finishedAtMs: number;
  severity: "success" | "emergency" | "warning";
};

type Options = {
  profileUid?: string;
  enabled: boolean;
  getIdToken: () => Promise<string>;
  onAlert?: (payload: CaregiverMealAlertPayload) => void;
};

function loadLastSeen(uid: string): number {
  try {
    const raw = localStorage.getItem(`${SEEN_KEY_PREFIX}${uid}`);
    if (!raw) return 0;
    const n = Number(raw);
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0;
  }
}

function saveLastSeen(uid: string, ms: number) {
  try {
    localStorage.setItem(`${SEEN_KEY_PREFIX}${uid}`, String(ms));
  } catch {
    /* ignore */
  }
}

export function useCaregiverMealAlerts({ profileUid, enabled, getIdToken, onAlert }: Options) {
  const lastSeenRef = useRef(0);
  const onAlertRef = useRef(onAlert);
  const firestoreLiveRef = useRef(false);

  useEffect(() => {
    onAlertRef.current = onAlert;
  }, [onAlert]);

  useEffect(() => {
    if (!enabled || !profileUid || typeof window === "undefined") return;

    lastSeenRef.current = loadLastSeen(profileUid);

    const deliver = (raw: unknown) => {
      const alert = parseCareAlert(raw);
      if (!alert || alert.finishedAtMs <= lastSeenRef.current) return;

      lastSeenRef.current = alert.finishedAtMs;
      saveLastSeen(profileUid, alert.finishedAtMs);

      const { title, body } = formatCareAlertNotification(alert);
      const severity =
        alert.type === "meal_emergency"
          ? "emergency"
          : alert.type === "plate_empty"
            ? "warning"
            : "success";
      onAlertRef.current?.({ title, body, finishedAtMs: alert.finishedAtMs, severity });
      if (document.visibilityState !== "visible") {
        showBrowserNotification(title, body, careAlertNotificationTag(alert));
      }
    };

    const poll = async () => {
      if (firestoreLiveRef.current) return;
      try {
        const token = await getIdToken();
        const since = lastSeenRef.current;
        const res = await fetch(`/api/alerts/caregiver?since=${since}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data = (await res.json()) as { alert?: CareAlertPayload | null };
        if (data.alert) deliver(data.alert);
      } catch {
        /* ignore */
      }
    };

    let channel: BroadcastChannel | undefined;
    try {
      if (typeof BroadcastChannel !== "undefined") {
        channel = new BroadcastChannel(MEAL_DONE_CHANNEL);
        channel.onmessage = (ev) => deliver(ev.data);
      }
    } catch {
      /* ignore */
    }

    const onCustom = (ev: Event) => {
      deliver((ev as CustomEvent).detail);
    };
    const onStorage = (ev: StorageEvent) => {
      if (ev.key !== MEAL_DONE_STORAGE_KEY || !ev.newValue) return;
      try {
        deliver(JSON.parse(ev.newValue));
      } catch {
        /* ignore */
      }
    };

    window.addEventListener("care-meal-finished", onCustom);
    window.addEventListener("storage", onStorage);

    let unsubFirestore: (() => void) | undefined;
    let unsubAuth: (() => void) | undefined;

    const attachFirestoreListener = () => {
      unsubFirestore?.();
      unsubFirestore = undefined;
      firestoreLiveRef.current = false;
      if (!isFirebaseConfigured()) return;

      try {
        const auth = getClientAuth();
        const user = auth.currentUser;
        if (!user) return;

        const ref = doc(getClientFirestore(), "carePairs", profileUid, "careAlerts", "latest");
        unsubFirestore = onSnapshot(
          ref,
          (snap) => {
            firestoreLiveRef.current = true;
            if (!snap.exists()) return;
            deliver(snap.data());
          },
          (err) => {
            firestoreLiveRef.current = false;
            console.warn("[caregiver alert] Firestore listen failed", err);
          },
        );
      } catch (err) {
        firestoreLiveRef.current = false;
        console.warn("[caregiver alert] Firestore setup failed", err);
      }
    };

    if (isFirebaseConfigured()) {
      try {
        const auth = getClientAuth();
        unsubAuth = onAuthStateChanged(auth, () => {
          attachFirestoreListener();
        });
      } catch (err) {
        console.warn("[caregiver alert] Firestore auth setup failed", err);
      }
    }

    void poll();
    const id = window.setInterval(() => void poll(), POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void poll();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("care-meal-finished", onCustom);
      window.removeEventListener("storage", onStorage);
      channel?.close();
      unsubFirestore?.();
      unsubAuth?.();
    };
  }, [profileUid, enabled, getIdToken]);
}
