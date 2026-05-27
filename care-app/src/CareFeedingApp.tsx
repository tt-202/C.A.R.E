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
  activeMealSlot,
  formatPlannedMealTime,
  MEAL_SLOTS,
  normalizeMealSchedule,
  type MealSchedule,
} from "@/lib/mealSchedule";
import { formatProfileSaveError, saveMealSchedule } from "@/lib/saveCareProfile";
import { notifyCaregiverMealFinished } from "@/lib/notifyCaregiver";
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

type CareFeedingAppProps = {
  role: UserRole;
  careRecipientName?: string;
  caregiverName?: string;
  userEmail?: string;
  profileUid?: string;
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

const AUTO_BITE_INTERVAL_MS = 30_000;

export default function CareFeedingApp({
  role,
  careRecipientName,
  caregiverName,
  userEmail,
  profileUid,
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
  const [sessionActive, setSessionActive] = useState(false);
  const [bitesCompleted, setBitesCompleted] = useState(0);
  const [mealSchedule, setMealSchedule] = useState<MealSchedule>(() =>
    normalizeMealSchedule(initialMealSchedule),
  );
  const [scheduleBusy, setScheduleBusy] = useState(false);
  const [scheduleMessage, setScheduleMessage] = useState<string | null>(null);
  const [activeReminder, setActiveReminder] = useState<string | null>(null);
  const [mealHistory, setMealHistory] = useState<MealHistoryEntry[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);
  const [startBusy, setStartBusy] = useState(false);

  const mealStartedAtRef = useRef<number | null>(null);
  const plannedMealTimeRef = useRef(
    formatPlannedMealTime(
      activeMealSlot(new Date(), normalizeMealSchedule(initialMealSchedule)).label,
      activeMealSlot(new Date(), normalizeMealSchedule(initialMealSchedule)).time,
    ),
  );
  const mealScheduleRef = useRef(mealSchedule);
  const mealIdRef = useRef<string | null>(null);
  const getIdTokenRef = useRef(getIdToken);
  const biteInFlight = useRef(false);

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
    const slot = activeMealSlot(new Date(), mealScheduleRef.current);
    plannedMealTimeRef.current = formatPlannedMealTime(slot.label, slot.time);
  }, [mealSchedule]);

  const handleInAppAlert = useCallback((payload: { body: string }) => {
    setActiveReminder(payload.body);
    window.setTimeout(() => setActiveReminder(null), 60_000);
  }, []);

  useMealReminders({
    schedule: mealSchedule,
    careRecipientName: careRecipientName ?? "User",
    enabled: !previewMode && !isUser,
    getIdToken,
    onReminder: handleInAppAlert,
  });

  useFcmPush({
    enabled: !previewMode && Boolean(profileUid) && !isUser,
    profileUid,
    role,
    getIdToken,
    onForegroundMessage: (body) => handleInAppAlert({ body }),
  });

  useCaregiverMealAlerts({
    profileUid,
    enabled: !previewMode && !isUser,
    getIdToken,
    onAlert: handleInAppAlert,
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
      profileUid,
      getIdTokenRef.current,
      careRecipientName,
      caregiverName,
      normalized,
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
      pushDetail += ` ${local.scheduled} reminder(s) scheduled on this device (15 min before meals, even if the tab is closed).`;
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
    if (!sessionActive) return "Not started. Press Start to begin.";
    return "Counting bites automatically…";
  }, [isUser, sessionActive]);

  const recordBite = useCallback(async () => {
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
        body: JSON.stringify({ sectionNum: 1 }),
      });
      if (!res.ok) throw new Error("bite failed");
      const data = (await res.json()) as { bitesTotal: number };
      setBitesCompleted(data.bitesTotal);
      void queueRobot("next_bite", { sectionNum: 1, mealId: mid });
    } catch {
      setBitesCompleted(prev);
      setApiError("Could not save a bite. Check your connection.");
    } finally {
      biteInFlight.current = false;
    }
  }, [previewMode, queueRobot, bitesCompleted]);

  const startSession = async () => {
    setApiError(null);
    if (mealStartedAtRef.current === null) {
      const slot = activeMealSlot(new Date(), mealScheduleRef.current);
      plannedMealTimeRef.current = formatPlannedMealTime(slot.label, slot.time);
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
  };

  const notifyCaregiverIfUserFinished = useCallback(
    async (bitesTotal: number, plannedMealTime: string) => {
      if (!isUser || previewMode) return;
      setDoneMessage(null);
      const result = await notifyCaregiverMealFinished(getIdTokenRef.current, {
        careRecipientName: careRecipientName ?? "User",
        caregiverName: caregiverName ?? "Caregiver",
        bitesTotal,
        plannedMealTime,
      });
      if (result.ok) {
        setDoneMessage(
          `${caregiverName ?? "Caregiver"} notified. Open the Caregiver screen on their device (or another tab) with notifications allowed.`,
        );
      } else {
        setApiError(`Could not notify caregiver: ${result.error}`);
      }
    },
    [isUser, previewMode, careRecipientName, caregiverName],
  );

  const finishMealOnServer = async () => {
    setApiError(null);
    setDoneMessage(null);
    setSessionActive(false);
    const bitesTotal = bitesCompleted;
    const plannedMealTime = plannedMealTimeRef.current;

    if (previewMode) {
      finalizeMealLocal();
      return;
    }

    const mid = mealIdRef.current;
    mealIdRef.current = null;
    mealStartedAtRef.current = null;
    setBitesCompleted(0);

    if (!mid) {
      await notifyCaregiverIfUserFinished(bitesTotal, plannedMealTime);
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
        body: JSON.stringify({ plannedMealTime }),
      });
      if (!res.ok) throw new Error("stop failed");
      await loadHistory();
      await notifyCaregiverIfUserFinished(bitesTotal, plannedMealTime);
    } catch {
      setApiError("Could not save this meal. Your next sync may show partial data.");
      await loadHistory();
      await notifyCaregiverIfUserFinished(bitesTotal, plannedMealTime);
    }
  };

  const emergencyStop = async () => {
    if (!isUser && mealStartedAtRef.current !== null) {
      await recordBite();
    }
    if (isUser && mealStartedAtRef.current === null) {
      await startSession();
    }
    void queueRobot("stop");
    await finishMealOnServer();
  };

  const doneMeal = async () => {
    if (isUser && mealStartedAtRef.current === null) {
      await startSession();
    }
    void queueRobot("stop");
    await finishMealOnServer();
  };

  useEffect(() => {
    if (isUser || !sessionActive) return;
    const id = window.setInterval(() => {
      void recordBite();
    }, AUTO_BITE_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [sessionActive, recordBite, isUser]);

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
          {welcomeName ? (
            <p className="mt-2 text-xl text-amber-100">
              Welcome, <span className="font-bold text-white">{welcomeName}</span>
            </p>
          ) : null}
          {!isUser && careRecipientName ? (
            <p className="mt-1 text-base text-amber-100/90">
              Helping <span className="font-semibold text-white">{careRecipientName}</span>
            </p>
          ) : null}
          <p className={`text-lg text-amber-100/95 ${welcomeName ? "mt-1" : "mt-2"}`}>
            {isUser
              ? "Press Done when you finish your meal."
              : "Set meal reminder times and track bites."}
          </p>
          {previewMode ? (
            <p className="mt-3 rounded-2xl border border-amber-300/40 bg-blue-950/50 px-4 py-2 text-base font-semibold text-amber-100">
              Preview mode — no server. History is stored only in this browser.
            </p>
          ) : null}
        </header>

        {apiError ? (
          <p
            className="rounded-2xl border-2 border-amber-800 bg-amber-100 px-4 py-3 text-center text-lg font-semibold text-amber-950"
            role="status"
          >
            {apiError}
          </p>
        ) : null}

        {activeReminder ? (
          <p
            className="rounded-2xl border-2 border-amber-400 bg-amber-200 px-4 py-3 text-center text-lg font-bold text-amber-950"
            role="alert"
          >
            {activeReminder}
          </p>
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
                <p className="col-span-full text-center text-base font-medium text-amber-100" role="status">
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
              <p className="text-center text-base font-medium text-amber-100/90">
                Set meal times for{" "}
                <span className="font-semibold text-white">{careRecipientName ?? "the user"}</span>.
                You&apos;ll get a notification <span className="font-semibold text-white">15 minutes before</span>{" "}
                each meal, and another when they tap <span className="font-semibold text-white">Done</span>.
                {isFcmConfigured()
                  ? "Firebase push is on — allow notifications when asked. Background alerts use your saved meal times."
                  : "Add NEXT_PUBLIC_FIREBASE_VAPID_KEY for background push, or keep this tab open for in-app alerts."}
              </p>

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
                  className="h-16 rounded-2xl border-2 border-red-900 bg-red-800 text-lg font-bold text-white hover:bg-red-900"
                  onClick={() => void emergencyStop()}
                >
                  <AlertTriangle className="mr-2 h-6 w-6" />
                  Emergency stop
                </Button>
              </div>
            </section>

            <section aria-labelledby="history-heading" className="space-y-4">
              <h2 id="history-heading" className="flex items-center justify-center gap-2 text-2xl font-bold text-amber-100">
                <History className="h-7 w-7" aria-hidden />
                User meal history
              </h2>
              <p className="text-center text-base text-amber-100/90">
                {previewMode ? "Saved on this device for " : "Saved in your account for "}
                <strong className="text-white">{careRecipientName ?? userEmail ?? "this account"}</strong>.
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
                    {mealHistory.length > 0 ? (
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
                      No finished meals yet. Press Start to count bites automatically, then use Emergency stop to end the meal.
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
                            Planned time: {entry.plannedMealTime ?? "—"} · Bites:{" "}
                            <span className="text-stone-950">{entry.bitesTotal}</span>
                          </p>
                          {entry.bitesTotal === 0 ? (
                            <p className="mt-2 text-sm text-stone-600">No bites recorded for this meal.</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </section>
          </>
        )}

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
