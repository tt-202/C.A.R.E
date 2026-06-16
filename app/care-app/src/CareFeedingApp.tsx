import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Play,
  Square,
  Clock,
  User,
  ShieldAlert,
  History,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { UserRole } from "./AuthPage";
import {
  type MealHistoryEntry,
  formatDuration,
  loadMealHistory,
  saveMealHistory,
} from "./mealHistoryStorage";
import { isRobotControlEnabled, sendRobotCommand } from "@/lib/robotClient";
import type { RobotCommandPayload, RobotCommandType } from "@/lib/robot";
import {
  formatPlannedMealDisplay,
  formatPlannedMealTime,
  MEAL_SLOTS,
  nextMealSlotAfter,
  normalizeMealSchedule,
  parsePlannedMealLabel,
  upcomingMealSlot,
  type MealSchedule,
  type PlannedMealSlot,
} from "@/lib/mealSchedule";
import { formatProfileSaveError, createUserInvite, saveMealSchedule } from "@/lib/saveCareProfile";
import { notifyCaregiverMealEmergency, notifyCaregiverMealFinished } from "@/lib/notifyCaregiver";
import { useCaregiverMealAlerts } from "@/hooks/useCaregiverMealAlerts";
import {
  getNotificationPermission,
  notificationBlockedHelp,
  requestMealReminderPermission,
  useMealReminders,
} from "@/hooks/useMealReminders";
import { useFcmPush } from "@/hooks/useFcmPush";
import { isFcmConfigured } from "@/lib/firebasePublicConfig";
import { setupPushOnThisDevice } from "@/lib/fcmDiagnostics";
import {
  minutesUntilNextReminder,
  scheduleLocalMealReminders,
} from "@/lib/scheduleLocalMealReminders";
import { REMINDER_LEAD_MINUTES } from "@/lib/mealReminderPush";
import { type Timestamp } from "firebase/firestore";
import { isFirebaseConfigured } from "@/lib/firebaseClient";
import { useRobotFirestore } from "@/hooks/useRobotFirestore";
import { getPublicRobotId } from "@/lib/robot";
import { feedCountTotal } from "@/lib/robotFirestorePaths";

function formatFirestoreTime(value: unknown): string {
  if (!value) return "—";
  if (typeof value === "object" && value !== null && "toDate" in value) {
    const ts = value as Timestamp;
    if (typeof ts.toDate === "function") return ts.toDate().toLocaleString();
  }
  if (typeof value === "object" && value !== null && "seconds" in value) {
    const seconds = (value as { seconds?: number }).seconds;
    if (typeof seconds === "number") return new Date(seconds * 1000).toLocaleString();
  }
  return "—";
}

type CareFeedingAppProps = {
  role: UserRole;
  careRecipientName?: string;
  caregiverName?: string;
  userEmail?: string;
  firebaseUid?: string;
  /** Shared care pair id for alerts and meals. */
  profileUid?: string;
  linkedUser?: boolean;
  initialMealSchedule?: MealSchedule;
  onMealScheduleSaved?: (schedule: MealSchedule) => void;
  /** No API calls — meal history stays in this browser (for local preview without Firebase/DB). */
  previewMode?: boolean;
  getIdToken: () => Promise<string>;
  onRoleChange?: (role: UserRole) => void;
  onSignOut?: () => void;
};

const roleLabels: Record<UserRole, string> = {
  caregiver: "Caregiver",
  user: "User",
};

export default function CareFeedingApp({
  role,
  careRecipientName,
  caregiverName,
  userEmail,
  firebaseUid,
  profileUid,
  linkedUser = false,
  initialMealSchedule,
  onMealScheduleSaved,
  previewMode = false,
  getIdToken,
  onRoleChange,
  onSignOut,
}: CareFeedingAppProps) {
  const isUser = role === "user";
  const welcomeName = isUser
    ? (careRecipientName ?? "User")
    : (caregiverName ?? "Caregiver");
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteMessage, setInviteMessage] = useState<string | null>(null);
  const [sessionActive, setSessionActive] = useState(false);
  const [bitesCompleted, setBitesCompleted] = useState(0);
  const [mealSchedule, setMealSchedule] = useState<MealSchedule>(() =>
    normalizeMealSchedule(initialMealSchedule),
  );
  const [scheduleBusy, setScheduleBusy] = useState(false);
  const [scheduleMessage, setScheduleMessage] = useState<string | null>(null);
  const [activeAlert, setActiveAlert] = useState<{
    title?: string;
    body: string;
    severity: "info" | "success" | "emergency";
  } | null>(null);
  const [mealHistory, setMealHistory] = useState<MealHistoryEntry[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);
  const [doneMessageEmergency, setDoneMessageEmergency] = useState(false);
  const [startBusy, setStartBusy] = useState(false);
  const [nextPlannedMeal, setNextPlannedMeal] = useState(() =>
    formatPlannedMealDisplay(upcomingMealSlot(new Date(), normalizeMealSchedule(initialMealSchedule))),
  );
  const robotId = getPublicRobotId();
  const { live: robotLive, feedCounts: robotFeedCounts, buttonInput: robotButtons, error: robotListenError } =
    useRobotFirestore({
      robotId,
      enabled: !previewMode && isFirebaseConfigured(),
    });

  const mealStartedAtRef = useRef<number | null>(null);
  const plannedMealTimeRef = useRef(
    formatPlannedMealTime(
      upcomingMealSlot(new Date(), normalizeMealSchedule(initialMealSchedule)).label,
      upcomingMealSlot(new Date(), normalizeMealSchedule(initialMealSchedule)).time,
    ),
  );
  const mealScheduleRef = useRef(mealSchedule);
  const mealIdRef = useRef<string | null>(null);
  const getIdTokenRef = useRef(getIdToken);
  const biteInFlight = useRef(false);
  const lastEatPressSeqRef = useRef(0);
  const feedPressHandling = useRef(false);

  const queueRobot = useCallback(
    async (cmd: RobotCommandType, payload?: RobotCommandPayload) => {
      if (previewMode || !isRobotControlEnabled()) return;
      try {
        await sendRobotCommand(getIdTokenRef.current, cmd, payload);
      } catch {
        console.warn("[robot]", cmd, "request failed");
      }
    },
    [previewMode],
  );

  mealScheduleRef.current = mealSchedule;
  getIdTokenRef.current = getIdToken;

  useEffect(() => {
    setMealSchedule(normalizeMealSchedule(initialMealSchedule));
  }, [initialMealSchedule]);

  useEffect(() => {
    if (sessionActive) return;
    const slot = upcomingMealSlot(new Date(), mealScheduleRef.current);
    plannedMealTimeRef.current = formatPlannedMealTime(slot.label, slot.time);
    setNextPlannedMeal(formatPlannedMealDisplay(slot));
  }, [mealSchedule, sessionActive]);

  const applyPlannedMealSlot = useCallback((slot: PlannedMealSlot) => {
    plannedMealTimeRef.current = formatPlannedMealTime(slot.label, slot.time);
    setNextPlannedMeal(formatPlannedMealDisplay(slot));
  }, []);

  const refreshMealReminders = useCallback(async () => {
    if (previewMode || isUser) return;
    const normalized = normalizeMealSchedule(mealScheduleRef.current);
    await scheduleLocalMealReminders(normalized, careRecipientName ?? "User");
  }, [previewMode, isUser, careRecipientName]);

  const handleInAppAlert = useCallback(
    (payload: { title?: string; body: string; severity?: "info" | "success" | "emergency" }) => {
      setActiveAlert({
        title: payload.title,
        body: payload.body,
        severity: payload.severity ?? "info",
      });
      window.setTimeout(() => setActiveAlert(null), 60_000);
    },
    [],
  );

  const handleMealReminder = useCallback(
    (payload: { title: string; body: string }) => {
      handleInAppAlert({ title: payload.title, body: payload.body, severity: "info" });
    },
    [handleInAppAlert],
  );

  useMealReminders({
    schedule: mealSchedule,
    careRecipientName: careRecipientName ?? "User",
    enabled: !previewMode && !isUser,
    getIdToken,
    onReminder: handleMealReminder,
  });

  useFcmPush({
    enabled: !previewMode && Boolean(firebaseUid) && !isUser,
    profileUid: firebaseUid,
    role,
    getIdToken,
    onForegroundMessage: (body) =>
      handleInAppAlert({
        body,
        severity: /emergency/i.test(body) ? "emergency" : "info",
      }),
  });

  useCaregiverMealAlerts({
    profileUid,
    enabled: !previewMode && !isUser,
    getIdToken,
    onAlert: (payload) =>
      handleInAppAlert({
        title: payload.title,
        body: payload.body,
        severity: payload.severity,
      }),
  });

  useEffect(() => {
    if (!previewMode && !isUser) {
      void requestMealReminderPermission();
    }
  }, [previewMode, isUser]);

  const saveReminderTimes = async () => {
    setScheduleMessage(null);
    setApiError(null);
    if (previewMode) {
      setScheduleMessage("Reminder times saved on this device (preview mode).");
      onMealScheduleSaved?.(mealSchedule);
      return;
    }
    if (!profileUid || !careRecipientName || !caregiverName) {
      setApiError("Could not save reminder times.");
      return;
    }
    setScheduleBusy(true);
    const ok = await requestMealReminderPermission();
    const normalized = normalizeMealSchedule(mealSchedule);
    const result = await saveMealSchedule(
      firebaseUid ?? profileUid ?? "",
      getIdTokenRef.current,
      careRecipientName,
      caregiverName,
      normalized,
      role,
      profileUid ?? "",
    );
    setScheduleBusy(false);
    if (!result.ok) {
      setApiError(formatProfileSaveError(result));
      return;
    }

    onMealScheduleSaved?.(normalized);

    const perm = getNotificationPermission();
    if (perm === "denied") {
      setScheduleMessage(`Times saved. ${notificationBlockedHelp()}`);
      return;
    }
    if (perm === "unsupported") {
      setScheduleMessage(
        "Times saved. This browser does not support notifications; use Chrome or Edge on desktop.",
      );
      return;
    }
    if (!ok) {
      setScheduleMessage("Times saved. Tap Allow when asked, then save again to enable push reminders.");
      return;
    }

    let pushDetail = "";
    if (isFcmConfigured()) {
      const setup = await setupPushOnThisDevice(getIdTokenRef.current, role);
      if (!setup.ok) {
        setScheduleMessage(
          `Times saved, but push setup failed: ${setup.error ?? "unknown error"}. Allow notifications and save again.`,
        );
        return;
      }
      pushDetail = " Server push is registered for this device.";
    }

    const local = await scheduleLocalMealReminders(normalized, careRecipientName ?? "User");
    if (local.scheduled > 0) {
      pushDetail += ` ${local.scheduled} reminder(s) scheduled on this device (${REMINDER_LEAD_MINUTES} min before meals, even if the tab is closed).`;
    } else if (local.supported) {
      pushDetail += " No more reminders today; tomorrow's will schedule when you open the app.";
    } else if (isFcmConfigured()) {
      pushDetail +=
        " Background alerts use server push (requires the app deployed on Vercel with CRON_SECRET).";
    } else {
      pushDetail += " Keep this tab open or deploy with Firebase for background alerts.";
    }

    const mins = minutesUntilNextReminder(normalized);
    const nextHint =
      mins !== null ? ` Next alert in about ${mins} minute${mins === 1 ? "" : "s"}.` : "";

    setScheduleMessage(`Reminder times saved.${pushDetail}${nextHint}`);
  };

  const loadHistory = useCallback(async () => {
    try {
      const token = await getIdTokenRef.current();
      if (!token) return;
      const res = await fetch("/api/meals/history", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = (await res.json()) as { meals?: MealHistoryEntry[] };
      setMealHistory(data.meals ?? []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!userEmail) return;
    if (previewMode) {
      setMealHistory(loadMealHistory(userEmail));
    } else {
      void loadHistory();
    }
  }, [userEmail, previewMode, loadHistory]);

  useEffect(() => {
    if (!previewMode || !userEmail) return;
    saveMealHistory(userEmail, mealHistory);
  }, [mealHistory, previewMode, userEmail]);

  const finalizeMealLocal = useCallback(() => {
    const start = mealStartedAtRef.current;
    if (start === null) {
      setSessionActive(false);
      return;
    }
    const end = Date.now();
    const durationMs = end - start;
    const bitesTotal = bitesCompleted;
    const tooShortEmpty = bitesTotal === 0 && durationMs < 3000;
    if (tooShortEmpty) {
      mealStartedAtRef.current = null;
      setBitesCompleted(0);
      setSessionActive(false);
      return;
    }
    const entry: MealHistoryEntry = {
      id: `${end}-${Math.random().toString(36).slice(2, 9)}`,
      endedAt: new Date(end).toISOString(),
      durationMs,
      bitesTotal,
      bySection: { 1: bitesTotal, 2: 0, 3: 0, 4: 0 },
      plannedMealTime: plannedMealTimeRef.current,
    };
    setMealHistory((prev) => [entry, ...prev]);
    mealStartedAtRef.current = null;
    setBitesCompleted(0);
    setSessionActive(false);
  }, [bitesCompleted]);

  const statusText = useMemo(() => {
    if (isUser) {
      if (!sessionActive) return "Press Done when you finish your meal.";
      return "Meal in progress — press Done when finished.";
    }
    if (!sessionActive) return "Press Start, then use the feed button for each bite.";
    return "Press the feed button on the robot for each bite.";
  }, [isUser, sessionActive]);

  const recordFeedPress = useCallback(
    async (feedPressSeq: number) => {
      const prev = bitesCompleted;
      const next = prev + 1;
      setBitesCompleted(next);

      if (previewMode) return;

      if (biteInFlight.current) return;
      biteInFlight.current = true;
      const mid = mealIdRef.current;
      if (!mid) {
        setBitesCompleted(prev);
        biteInFlight.current = false;
        return;
      }
      try {
        const token = await getIdTokenRef.current();
        const res = await fetch(`/api/meals/${mid}/bite`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ sectionNum: 1, feedPressSeq }),
        });
        if (!res.ok) throw new Error("bite failed");
        const data = (await res.json()) as { bitesTotal: number };
        setBitesCompleted(data.bitesTotal);
      } catch {
        setBitesCompleted(prev);
        setApiError("Could not save a bite. Check your connection.");
      } finally {
        biteInFlight.current = false;
      }
    },
    [previewMode, bitesCompleted],
  );

  const startSession = useCallback(async () => {
    setApiError(null);
    if (mealStartedAtRef.current === null) {
      const slot = upcomingMealSlot(new Date(), mealScheduleRef.current);
      applyPlannedMealSlot(slot);
      if (previewMode) {
        mealStartedAtRef.current = Date.now();
        setBitesCompleted(0);
      } else {
        setStartBusy(true);
        try {
          const token = await getIdTokenRef.current();
          const res = await fetch("/api/meals/start", {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ plannedMealTime: plannedMealTimeRef.current }),
          });
          if (!res.ok) throw new Error("start failed");
          const data = (await res.json()) as { mealId: string };
          mealIdRef.current = data.mealId;
          mealStartedAtRef.current = Date.now();
          setBitesCompleted(0);
        } catch {
          setApiError("Could not start a meal. Check your connection and sign-in.");
          setStartBusy(false);
          return;
        }
        setStartBusy(false);
      }
    }
    setSessionActive(true);
  }, [previewMode, applyPlannedMealSlot]);

  const resetPlannedMealSlot = useCallback(
    (justCompletedPlanned?: string) => {
      const completedLabel = parsePlannedMealLabel(
        justCompletedPlanned ?? plannedMealTimeRef.current,
      );
      applyPlannedMealSlot(nextMealSlotAfter(completedLabel, mealScheduleRef.current));
    },
    [applyPlannedMealSlot],
  );

  const notifyCaregiverAfterMealEnd = useCallback(
    async (bitesTotal: number, plannedMealTime: string, emergency: boolean) => {
      if (!isUser || previewMode) return;
      const payload = {
        careRecipientName: careRecipientName ?? "User",
        caregiverName: caregiverName ?? "Caregiver",
        bitesTotal,
        plannedMealTime,
      };
      const result = emergency
        ? await notifyCaregiverMealEmergency(getIdTokenRef.current, payload)
        : await notifyCaregiverMealFinished(getIdTokenRef.current, payload);
      if (!result.ok) {
        setApiError(
          emergency
            ? `Could not send emergency alert to caregiver: ${result.error}`
            : `Could not notify caregiver: ${result.error}`,
        );
      }
    },
    [isUser, previewMode, careRecipientName, caregiverName],
  );

  const ensureMealSessionForEnd = useCallback(async () => {
    if (previewMode) {
      if (mealStartedAtRef.current === null) {
        const slot = upcomingMealSlot(new Date(), mealScheduleRef.current);
        applyPlannedMealSlot(slot);
        mealStartedAtRef.current = Date.now();
        setBitesCompleted(0);
      }
      setSessionActive(true);
      return;
    }
    if (!mealIdRef.current) {
      await startSession();
    }
  }, [previewMode, startSession, applyPlannedMealSlot]);

  const finishMealOnServer = async (opts: { complete: boolean; emergency: boolean }) => {
    setApiError(null);
    setDoneMessage(null);
    setDoneMessageEmergency(false);
    const bitesTotal = bitesCompleted;
    const plannedMealTime = plannedMealTimeRef.current;

    if (previewMode) {
      finalizeMealLocal();
      resetPlannedMealSlot(plannedMealTime);
      return;
    }

    const mid = mealIdRef.current;
    if (!mid) {
      setSessionActive(false);
      setBitesCompleted(0);
      mealStartedAtRef.current = null;
      resetPlannedMealSlot(plannedMealTime);
      await notifyCaregiverAfterMealEnd(bitesTotal, plannedMealTime, opts.emergency);
      return;
    }

    try {
      const token = await getIdTokenRef.current();
      const res = await fetch(`/api/meals/${mid}/stop`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          plannedMealTime,
          complete: opts.complete,
          emergency: opts.emergency,
        }),
      });
      const data = (await res.json()) as {
        meal?: MealHistoryEntry;
        cancelled?: boolean;
        error?: string;
      };
      if (!res.ok && !data.cancelled) throw new Error("stop failed");

      mealIdRef.current = null;
      mealStartedAtRef.current = null;
      setBitesCompleted(0);
      setSessionActive(false);
      resetPlannedMealSlot(plannedMealTime);
      void refreshMealReminders();

      if (data.meal) {
        setMealHistory((prev) => [data.meal!, ...prev.filter((e) => e.id !== data.meal!.id)]);
        const endedLabel = new Date(data.meal.endedAt).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        });
        const nextLabel = formatPlannedMealDisplay(
          nextMealSlotAfter(parsePlannedMealLabel(plannedMealTime), mealScheduleRef.current),
        );
        if (opts.emergency) {
          setDoneMessageEmergency(true);
          setDoneMessage(
            isUser
              ? `Emergency recorded at ${endedLabel}. Your caregiver has been notified. Next: ${nextLabel}.`
              : `Emergency stop saved for ${careRecipientName ?? "user"} at ${endedLabel}. Next: ${nextLabel}.`,
          );
        } else {
          setDoneMessage(
            isUser
              ? `Meal saved at ${endedLabel}. Next: ${nextLabel}.`
              : `Meal saved for ${careRecipientName ?? "user"} at ${endedLabel}. Next: ${nextLabel}.`,
          );
        }
      } else {
        await loadHistory();
      }

      await notifyCaregiverAfterMealEnd(bitesTotal, plannedMealTime, opts.emergency);
    } catch {
      setApiError("Could not save this meal. Your next sync may show partial data.");
      mealIdRef.current = null;
      mealStartedAtRef.current = null;
      setBitesCompleted(0);
      setSessionActive(false);
      resetPlannedMealSlot(plannedMealTime);
      void refreshMealReminders();
      await loadHistory();
      await notifyCaregiverAfterMealEnd(bitesTotal, plannedMealTime, opts.emergency);
    }
  };

  const endMeal = async (emergency: boolean) => {
    await ensureMealSessionForEnd();
    void queueRobot("stop", { emergency });
    await finishMealOnServer({ complete: true, emergency });
  };

  const emergencyStop = async () => {
    await endMeal(true);
  };

  const doneMeal = async () => {
    await endMeal(false);
  };

  useEffect(() => {
    if (previewMode) return;
    const seq = robotButtons?.eat_press_seq;
    if (typeof seq !== "number" || seq <= lastEatPressSeqRef.current) return;
    if (feedPressHandling.current) return;

    feedPressHandling.current = true;
    lastEatPressSeqRef.current = seq;

    void (async () => {
      try {
        if (!sessionActive) {
          await startSession();
        }
        await recordFeedPress(seq);
      } finally {
        feedPressHandling.current = false;
      }
    })();
  }, [previewMode, robotButtons?.eat_press_seq, sessionActive, startSession, recordFeedPress]);

  const clearHistory = async () => {
    if (!userEmail) return;
    if (!window.confirm("Clear all saved meal history for this account?")) return;
    if (previewMode) {
      setMealHistory([]);
      saveMealHistory(userEmail, []);
      return;
    }
    try {
      const token = await getIdTokenRef.current();
      const res = await fetch("/api/meals/history", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setMealHistory([]);
    } catch {
      setApiError("Could not clear history.");
    }
  };

  const totalMeals = mealHistory.length;
  const totalBitesRecorded = useMemo(
    () => mealHistory.reduce((sum, m) => sum + m.bitesTotal, 0),
    [mealHistory]
  );

  return (
    <div className="min-h-screen p-4 pb-10 text-zinc-900 md:p-8">
      <div className="mx-auto flex max-w-lg flex-col gap-6">
        <header className="text-center">
          <p className="text-sm font-bold uppercase tracking-widest text-amber-200">C.A.R.E</p>

          {onRoleChange ? (
            <div className="mx-auto mt-4 grid w-full max-w-md grid-cols-2 gap-3">
              <Button
                type="button"
                onClick={() => onRoleChange("user")}
                className={cn(
                  "h-14 rounded-2xl border-2 text-base font-bold md:text-lg",
                  role === "user"
                    ? "border-blue-950 bg-blue-900 text-white shadow-md hover:bg-blue-950"
                    : "border-stone-500 bg-stone-200 text-stone-900 hover:bg-stone-100"
                )}
                aria-pressed={role === "user"}
              >
                <User className="mr-2 h-5 w-5 shrink-0" aria-hidden />
                User
              </Button>
              <Button
                type="button"
                onClick={() => onRoleChange("caregiver")}
                className={cn(
                  "h-14 rounded-2xl border-2 text-base font-bold md:text-lg",
                  role === "caregiver"
                    ? "border-blue-950 bg-blue-900 text-white shadow-md hover:bg-blue-950"
                    : "border-stone-500 bg-stone-200 text-stone-900 hover:bg-stone-100"
                )}
                aria-pressed={role === "caregiver"}
              >
                <ShieldAlert className="mr-2 h-5 w-5 shrink-0" aria-hidden />
                Caregiver
              </Button>
            </div>
          ) : (
            <div className="mt-2 inline-flex rounded-full border-2 border-amber-200/50 bg-blue-950/60 px-4 py-1.5 text-sm font-bold text-amber-100">
              {roleLabels[role]} mode
            </div>
          )}

          <h1 className="mt-4 text-3xl font-bold tracking-tight text-white md:text-4xl">Meal helper</h1>
          {isUser ? (
            <div className="mt-3 space-y-1">
              {careRecipientName ? (
                <p className="text-xl text-amber-100">
                  User: <span className="font-bold text-white">{careRecipientName}</span>
                </p>
              ) : null}
              {caregiverName ? (
                <p className="text-xl text-amber-100">
                  Caregiver: <span className="font-bold text-white">{caregiverName}</span>
                </p>
              ) : null}
            </div>
          ) : (
            <>
              {welcomeName ? (
                <p className="mt-2 text-xl text-amber-100">
                  Welcome, <span className="font-bold text-white">{welcomeName}</span>
                </p>
              ) : null}
              {careRecipientName ? (
                <p className="mt-1 text-base text-amber-100/90">
                  Helping <span className="font-semibold text-white">{careRecipientName}</span>
                </p>
              ) : null}
            </>
          )}
          <p className={`text-lg text-amber-100/95 ${welcomeName ? "mt-1" : "mt-2"}`}>
            {isUser
              ? "Press Done when you finish your meal."
              : "Start a meal, then each feed-button press counts as one bite."}
          </p>
          {previewMode ? (
            <p className="mt-3 rounded-2xl border border-amber-300/40 bg-blue-950/50 px-4 py-2 text-base font-semibold text-amber-100">
              Preview mode — no server. History is stored only in this browser.
            </p>
          ) : null}
        </header>

        {!previewMode && !isUser ? (
          <Card className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] shadow-lg">
            <CardContent className="space-y-3 p-5">
              <h2 className="text-lg font-bold text-stone-950">Robot live status</h2>
              <p className="text-sm font-medium text-stone-700">
                Firestore <span className="font-mono text-stone-900">robots/{robotId}</span> — updates when the Jetson
                writes stats.
              </p>
              {robotListenError ? (
                <p className="rounded-xl border-2 border-red-700 bg-red-100 px-3 py-2 text-sm font-medium text-red-950">
                  {robotListenError}
                </p>
              ) : null}
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                <dt className="font-semibold text-stone-700">Jetson online</dt>
                <dd className="font-bold text-stone-950">
                  {robotLive?.jetson_online ? "Yes" : robotLive ? "No" : "Waiting…"}
                </dd>
                <dt className="font-semibold text-stone-700">Robot state</dt>
                <dd className="font-bold text-stone-950">{robotLive?.state ?? "—"}</dd>
                <dt className="font-semibold text-stone-700">This meal bites</dt>
                <dd className="font-bold text-stone-950">
                  {typeof robotLive?.bite_count === "number" ? robotLive.bite_count : 0}
                </dd>
                <dt className="font-semibold text-stone-700">Lifetime feeds</dt>
                <dd className="font-bold text-stone-950">{feedCountTotal(robotFeedCounts)}</dd>
                <dt className="font-semibold text-stone-700">Current section</dt>
                <dd className="font-bold text-stone-950">
                  {typeof robotLive?.section === "number" ? robotLive.section : "—"}
                </dd>
                <dt className="font-semibold text-stone-700">Emergency</dt>
                <dd className="font-bold text-stone-950">
                  {robotLive?.emergency ? "Yes" : robotLive ? "No" : "—"}
                </dd>
                <dt className="font-semibold text-stone-700">Successful feeds</dt>
                <dd className="font-bold text-stone-950">{robotFeedCounts?.successful_feeds ?? "—"}</dd>
                <dt className="font-semibold text-stone-700">Failed feeds</dt>
                <dd className="font-bold text-stone-950">{robotFeedCounts?.failed_feeds ?? "—"}</dd>
                <dt className="font-semibold text-stone-700">Feed button presses</dt>
                <dd className="font-bold text-stone-950">
                  {typeof robotButtons?.eat_press_seq === "number" ? robotButtons.eat_press_seq : "—"}
                </dd>
                <dt className="font-semibold text-stone-700">Eat pressed</dt>
                <dd className="font-bold text-stone-950">
                  {robotButtons?.eat_pressed ? "Yes" : robotButtons ? "No" : "—"}
                </dd>
                <dt className="font-semibold text-stone-700">Stop pressed</dt>
                <dd className="font-bold text-stone-950">
                  {robotButtons?.stop_pressed ? "Yes" : robotButtons ? "No" : "—"}
                </dd>
                <dt className="col-span-2 font-semibold text-stone-700">Last feed</dt>
                <dd className="col-span-2 font-bold text-stone-950">
                  {formatFirestoreTime(robotLive?.last_feed_time)}
                </dd>
              </dl>
            </CardContent>
          </Card>
        ) : null}

        {!previewMode && !isUser && !linkedUser ? (
          <Card className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] shadow-lg">
            <CardContent className="space-y-4 p-6">
              <h2 className="text-xl font-bold text-stone-950">Invite the user</h2>
              <p className="text-base text-stone-800">
                Share this code so they can sign up with their own email and join your care pair.
              </p>
              {inviteCode ? (
                <p className="rounded-2xl border-2 border-stone-600 bg-white px-4 py-4 text-center text-3xl font-bold tracking-[0.3em] text-stone-950">
                  {inviteCode}
                </p>
              ) : null}
              {inviteMessage ? (
                <p className="text-center text-base font-medium text-stone-700">{inviteMessage}</p>
              ) : null}
              <Button
                type="button"
                disabled={inviteBusy}
                className="h-14 w-full rounded-2xl border-2 border-blue-950 bg-blue-900 text-lg font-semibold text-white hover:bg-blue-950"
                onClick={async () => {
                  setInviteBusy(true);
                  setInviteMessage(null);
                  const result = await createUserInvite(getIdToken);
                  setInviteBusy(false);
                  if (!result.ok) {
                    setInviteMessage(result.error);
                    return;
                  }
                  setInviteCode(result.code);
                  setInviteMessage("Code expires in 7 days. They choose Join with invite at sign-in.");
                }}
              >
                {inviteCode ? "Generate new invite code" : "Create invite code"}
              </Button>
            </CardContent>
          </Card>
        ) : null}

        {apiError ? (
          <p
            className="rounded-2xl border-2 border-amber-800 bg-amber-100 px-4 py-3 text-center text-lg font-semibold text-amber-950"
            role="status"
          >
            {apiError}
          </p>
        ) : null}

        {activeAlert ? (
          <div
            className={cn(
              "rounded-2xl border-2 px-4 py-3 text-center shadow-md",
              activeAlert.severity === "emergency"
                ? "border-red-700 bg-red-100 text-red-950"
                : activeAlert.severity === "success"
                  ? "border-green-700 bg-green-100 text-green-950"
                  : "border-amber-400 bg-amber-200 text-amber-950",
            )}
            role="alert"
          >
            {activeAlert.severity === "emergency" ? (
              <p className="flex items-center justify-center gap-2 text-lg font-black uppercase tracking-wide">
                <AlertTriangle className="h-6 w-6 shrink-0" aria-hidden />
                Emergency
              </p>
            ) : null}
            {activeAlert.title ? (
              <p
                className={cn(
                  "font-bold",
                  activeAlert.severity === "emergency" ? "text-xl" : "text-lg",
                )}
              >
                {activeAlert.title}
              </p>
            ) : null}
            <p className={cn("font-semibold", activeAlert.title ? "mt-1 text-base" : "text-lg")}>
              {activeAlert.body}
            </p>
          </div>
        ) : null}

        {isUser ? (
          <>
            <div className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] p-6 shadow-lg">
              <p className="text-center text-lg font-medium text-stone-800">{statusText}</p>
            </div>

            <section aria-labelledby="user-actions" className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <h2 id="user-actions" className="col-span-full text-center text-2xl font-bold text-amber-100">
                Actions
              </h2>
              <Button
                type="button"
                className="h-16 rounded-2xl border-2 border-blue-950 bg-blue-900 text-lg font-bold text-white hover:bg-blue-950"
                onClick={() => void doneMeal()}
              >
                <Square className="mr-2 h-6 w-6" />
                Done
              </Button>
              <Button
                type="button"
                className="h-16 rounded-2xl border-2 border-red-900 bg-red-800 text-lg font-bold text-white hover:bg-red-900"
                onClick={() => void emergencyStop()}
              >
                <AlertTriangle className="mr-2 h-6 w-6" />
                Emergency stop
              </Button>
              {doneMessage ? (
                <p
                  className={cn(
                    "col-span-full rounded-2xl border-2 px-4 py-3 text-center text-base font-bold",
                    doneMessageEmergency
                      ? "border-red-800 bg-red-100 text-red-950"
                      : "border-transparent text-amber-100 font-medium",
                  )}
                  role="status"
                >
                  {doneMessageEmergency ? (
                    <span className="mb-1 flex items-center justify-center gap-2 text-lg font-black uppercase">
                      <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden />
                      Emergency
                    </span>
                  ) : null}
                  {doneMessage}
                </p>
              ) : null}
            </section>
          </>
        ) : (
          <>
            <div className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] p-6 shadow-lg">
              <p className="text-center text-3xl font-black tabular-nums text-stone-950">
                Bites: {bitesCompleted}
              </p>
              <p className="mt-2 text-center text-lg font-medium text-stone-800">{statusText}</p>
            </div>

            <section className="space-y-4" aria-labelledby="schedule-heading">
              <h2 id="schedule-heading" className="text-center text-2xl font-bold text-amber-100">
                Meal reminders
              </h2>

              <div className="rounded-2xl border-2 border-amber-500/60 bg-[#f5ebe0] p-4 text-center shadow-md">
                <p className="text-sm font-bold text-stone-700">
                  {sessionActive ? "Current meal on schedule" : "Next meal on schedule"}
                </p>
                <p className="mt-1 text-2xl font-black text-stone-950">{nextPlannedMeal}</p>
                <p className="mt-2 text-sm font-medium text-stone-700">
                  After Done (meal complete) or Emergency stop, the schedule moves to the next meal.
                </p>
              </div>

              <div className="space-y-3">
                {MEAL_SLOTS.map((slot) => (
                  <div
                    key={slot.key}
                    className="rounded-2xl border-2 border-stone-600 bg-[#f5ebe0] p-4 shadow-md"
                  >
                    <label
                      htmlFor={`meal-time-${slot.key}`}
                      className="flex items-center justify-center gap-2 text-lg font-bold text-stone-950"
                    >
                      <Clock className="h-5 w-5 shrink-0" aria-hidden />
                      {slot.label}
                    </label>
                    <Input
                      id={`meal-time-${slot.key}`}
                      type="time"
                      value={mealSchedule[slot.field]}
                      onChange={(e) =>
                        setMealSchedule((prev) => ({
                          ...prev,
                          [slot.field]: e.target.value,
                        }))
                      }
                      className="mt-3 h-14 rounded-2xl border-2 border-stone-600 bg-[#fffefb] text-center text-2xl font-bold tabular-nums text-stone-950 focus-visible:border-blue-800"
                    />
                  </div>
                ))}
              </div>

              <Button
                type="button"
                disabled={scheduleBusy}
                className="h-14 w-full rounded-2xl border-2 border-stone-700 bg-stone-800 text-lg font-semibold text-white hover:bg-stone-900 disabled:opacity-60"
                onClick={() => void saveReminderTimes()}
              >
                Save reminder times
              </Button>
              {scheduleMessage ? (
                <p className="text-center text-base font-medium text-amber-100" role="status">
                  {scheduleMessage}
                </p>
              ) : null}
            </section>

            <section aria-labelledby="controls-heading">
              <h2 id="controls-heading" className="mb-3 text-center text-2xl font-bold text-amber-100">
                Controls
              </h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Button
                  type="button"
                  disabled={startBusy}
                  className="h-16 rounded-2xl border-2 border-blue-950 bg-blue-900 text-lg font-semibold text-white hover:bg-blue-950 disabled:opacity-60"
                  onClick={() => void startSession()}
                >
                  <Play className="mr-2 h-6 w-6" />
                  Start
                </Button>
                <Button
                  type="button"
                  className="h-16 rounded-2xl border-2 border-blue-950 bg-blue-900 text-lg font-semibold text-white hover:bg-blue-950"
                  onClick={() => void doneMeal()}
                >
                  <Square className="mr-2 h-6 w-6" />
                  Done
                </Button>
                <Button
                  type="button"
                  className="col-span-full h-16 rounded-2xl border-2 border-red-900 bg-red-800 text-lg font-bold text-white hover:bg-red-900"
                  onClick={() => void emergencyStop()}
                >
                  <AlertTriangle className="mr-2 h-6 w-6" />
                  Emergency stop
                </Button>
              </div>
              {doneMessage ? (
                <p
                  className={cn(
                    "rounded-2xl border-2 px-4 py-3 text-center text-base font-bold",
                    doneMessageEmergency
                      ? "border-red-800 bg-red-100 text-red-950"
                      : "font-medium text-amber-100",
                  )}
                  role="status"
                >
                  {doneMessageEmergency ? (
                    <span className="mb-1 flex items-center justify-center gap-2 text-lg font-black uppercase">
                      <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden />
                      Emergency
                    </span>
                  ) : null}
                  {doneMessage}
                </p>
              ) : null}
            </section>
          </>
        )}

        {!previewMode ? (
          <section aria-labelledby="history-heading" className="space-y-4">
            <h2 id="history-heading" className="flex items-center justify-center gap-2 text-2xl font-bold text-amber-100">
              <History className="h-7 w-7" aria-hidden />
              {isUser ? "My meal history" : "User meal history"}
            </h2>
            <p className="text-center text-base text-amber-100/90">
              Meals saved when someone taps <strong className="text-white">Done</strong> (meal complete) or{" "}
              <strong className="text-white">Emergency stop</strong> (alerts caregiver). Bites come from each{" "}
              <strong className="text-white">feed button</strong> press on the robot.
            </p>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border-2 border-stone-600 bg-[#f5ebe0] p-4 text-center shadow-md">
                <p className="text-sm font-bold text-stone-700">Meals recorded</p>
                <p className="mt-1 text-3xl font-black tabular-nums text-stone-950">{totalMeals}</p>
              </div>
              <div className="rounded-2xl border-2 border-stone-600 bg-[#f5ebe0] p-4 text-center shadow-md">
                <p className="text-sm font-bold text-stone-700">Total bites (history)</p>
                <p className="mt-1 text-3xl font-black tabular-nums text-stone-950">{totalBitesRecorded}</p>
              </div>
              <div className="rounded-2xl border-2 border-stone-600 bg-[#f5ebe0] p-4 text-center shadow-md sm:col-span-1">
                <p className="text-sm font-bold text-stone-700">Latest meal length</p>
                <p className="mt-1 text-xl font-bold leading-tight text-stone-950">
                  {mealHistory[0] ? formatDuration(mealHistory[0].durationMs) : "—"}
                </p>
              </div>
            </div>

            <Card className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] shadow-lg">
              <CardContent className="space-y-4 p-5 md:p-6">
                <div className="flex flex-col items-center justify-between gap-3 sm:flex-row">
                  <p className="text-lg font-bold text-stone-950">Past meals (newest first)</p>
                  {!isUser && mealHistory.length > 0 ? (
                    <Button
                      type="button"
                      variant="outline"
                      className="rounded-2xl border-2 border-stone-600 bg-stone-200 text-stone-900 hover:bg-stone-100"
                      onClick={() => void clearHistory()}
                    >
                      Clear history
                    </Button>
                  ) : null}
                </div>

                {mealHistory.length === 0 ? (
                  <p className="text-center text-lg font-medium text-stone-700">
                    No finished meals yet. Tap Done or Emergency stop when the meal is finished.
                  </p>
                ) : (
                  <ul className="max-h-[28rem] space-y-4 overflow-y-auto pr-1">
                    {mealHistory.map((entry) => (
                      <li
                        key={entry.id}
                        className="rounded-2xl border-2 border-stone-500 bg-[#fffefb] p-4 text-stone-900 shadow-sm"
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-stone-200 pb-2">
                          <span className="text-base font-bold">
                            Finished{" "}
                            {new Date(entry.endedAt).toLocaleString(undefined, {
                              dateStyle: "medium",
                              timeStyle: "short",
                            })}
                          </span>
                          <span className="text-lg font-black text-blue-900">
                            {formatDuration(entry.durationMs)}
                          </span>
                        </div>
                        <p className="mt-2 text-base font-semibold text-stone-700">
                          Planned: {entry.plannedMealTime ?? "—"} · Bites:{" "}
                          <span className="text-stone-950">{entry.bitesTotal}</span>
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </section>
        ) : null}

        {onSignOut ? (
          <div className="border-t border-amber-200/30 pt-6 text-center">
            <Button
              type="button"
              variant="ghost"
              className="h-12 text-lg font-medium text-amber-100 underline-offset-4 hover:bg-white/10 hover:text-white"
              onClick={onSignOut}
            >
              Sign out
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
