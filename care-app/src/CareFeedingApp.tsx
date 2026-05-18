import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Play,
  Pause,
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

/** Four plate sections: numbered 1–4 for the user; labels for caregiver. */
const PLATE_SECTIONS = [
  { num: 1 as const, id: "A", name: "Vegetables", hint: "Salad, greens" },
  { num: 2 as const, id: "B", name: "Main dish", hint: "Meat, fish, tofu" },
  { num: 3 as const, id: "C", name: "Rice or potato", hint: "Starch" },
  { num: 4 as const, id: "D", name: "Fruit", hint: "Dessert" },
] as const;

type SectionNum = (typeof PLATE_SECTIONS)[number]["num"];

type CareFeedingAppProps = {
  role: UserRole;
  userName?: string;
  userEmail?: string;
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
  userName,
  userEmail,
  previewMode = false,
  getIdToken,
  onRoleChange,
  onSignOut,
}: CareFeedingAppProps) {
  const [selectedSection, setSelectedSection] = useState<SectionNum>(2);
  const selectedSectionRef = useRef<SectionNum>(selectedSection);
  useEffect(() => {
    selectedSectionRef.current = selectedSection;
  }, [selectedSection]);

  const [sessionActive, setSessionActive] = useState(false);
  const [bitesCompleted, setBitesCompleted] = useState(0);
  const [mealTime, setMealTime] = useState("12:00");
  const [biteSectionStack, setBiteSectionStack] = useState<SectionNum[]>([]);
  const [mealHistory, setMealHistory] = useState<MealHistoryEntry[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);
  const [startBusy, setStartBusy] = useState(false);

  const mealStartedAtRef = useRef<number | null>(null);
  const biteSectionStackRef = useRef<SectionNum[]>([]);
  const mealTimeRef = useRef(mealTime);
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

  mealTimeRef.current = mealTime;
  getIdTokenRef.current = getIdToken;

  useEffect(() => {
    biteSectionStackRef.current = biteSectionStack;
  }, [biteSectionStack]);

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
    const stack = biteSectionStackRef.current;
    if (start === null) {
      setSessionActive(false);
      return;
    }
    const end = Date.now();
    const durationMs = end - start;
    const bitesTotal = stack.length;
    const bySection: Record<1 | 2 | 3 | 4, number> = { 1: 0, 2: 0, 3: 0, 4: 0 };
    for (const s of stack) {
      bySection[s] += 1;
    }
    const tooShortEmpty = bitesTotal === 0 && durationMs < 3000;
    if (tooShortEmpty) {
      mealStartedAtRef.current = null;
      setBiteSectionStack([]);
      biteSectionStackRef.current = [];
      setBitesCompleted(0);
      setSessionActive(false);
      return;
    }
    const entry: MealHistoryEntry = {
      id: `${end}-${Math.random().toString(36).slice(2, 9)}`,
      endedAt: new Date(end).toISOString(),
      durationMs,
      bitesTotal,
      bySection,
      plannedMealTime: mealTimeRef.current,
    };
    setMealHistory((prev) => [entry, ...prev]);
    mealStartedAtRef.current = null;
    setBiteSectionStack([]);
    biteSectionStackRef.current = [];
    setBitesCompleted(0);
    setSessionActive(false);
  }, []);

  const selectedMeta = PLATE_SECTIONS.find((s) => s.num === selectedSection) ?? PLATE_SECTIONS[1];

  const statusText = useMemo(() => {
    if (mealStartedAtRef.current === null) return "Not started.";
    if (!sessionActive) return "Paused. Press Start to continue or Stop to finish.";
    return "Counting bites...";
  }, [sessionActive]);

  const recordBite = useCallback(async () => {
    const sec = selectedSectionRef.current;
    const prev = biteSectionStackRef.current;
    const next = [...prev, sec];
    biteSectionStackRef.current = next;
    setBiteSectionStack(next);
    setBitesCompleted(next.length);

    if (previewMode) return;

    if (biteInFlight.current) return;
    biteInFlight.current = true;
    const mid = mealIdRef.current;
    if (!mid) {
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
        body: JSON.stringify({ sectionNum: sec }),
      });
      if (!res.ok) throw new Error("bite failed");
      const data = (await res.json()) as { bitesTotal: number };
      setBitesCompleted(data.bitesTotal);
      void queueRobot("next_bite", { sectionNum: sec, mealId: mid });
    } catch {
      biteSectionStackRef.current = prev;
      setBiteSectionStack(prev);
      setBitesCompleted(prev.length);
      setApiError("Could not save a bite. Check your connection.");
    } finally {
      biteInFlight.current = false;
    }
  }, [previewMode, queueRobot]);

  const startSession = async () => {
    setApiError(null);
    if (mealStartedAtRef.current === null) {
      if (previewMode) {
        mealStartedAtRef.current = Date.now();
        setBiteSectionStack([]);
        biteSectionStackRef.current = [];
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
            body: JSON.stringify({ plannedMealTime: mealTimeRef.current }),
          });
          if (!res.ok) throw new Error("start failed");
          const data = (await res.json()) as { mealId: string };
          mealIdRef.current = data.mealId;
          mealStartedAtRef.current = Date.now();
          setBiteSectionStack([]);
          biteSectionStackRef.current = [];
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

  const pauseSession = () => {
    setSessionActive(false);
    void queueRobot("pause");
  };

  const finishMealOnServer = async () => {
    setApiError(null);
    setSessionActive(false);
    if (previewMode) {
      finalizeMealLocal();
      return;
    }

    const mid = mealIdRef.current;
    mealIdRef.current = null;
    mealStartedAtRef.current = null;
    setBiteSectionStack([]);
    biteSectionStackRef.current = [];
    setBitesCompleted(0);

    if (!mid) return;
    try {
      const token = await getIdTokenRef.current();
      const res = await fetch(`/api/meals/${mid}/stop`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ plannedMealTime: mealTimeRef.current }),
      });
      if (!res.ok) throw new Error("stop failed");
      await loadHistory();
    } catch {
      setApiError("Could not save this meal. Your next sync may show partial data.");
      await loadHistory();
    }
  };

  const stopSession = async () => {
    if (mealStartedAtRef.current !== null) {
      await recordBite();
    }
    void queueRobot("stop");
    await finishMealOnServer();
  };

  const emergencyStop = async () => {
    if (mealStartedAtRef.current !== null) {
      await recordBite();
    }
    void queueRobot("stop");
    await finishMealOnServer();
  };

  useEffect(() => {
    if (!sessionActive) return;
    const id = window.setInterval(() => {
      void recordBite();
    }, AUTO_BITE_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [sessionActive, recordBite]);

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

  const isUser = role === "user";

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
          {userName ? (
            <p className="mt-2 text-xl text-amber-100">
              Welcome, <span className="font-bold text-white">{userName}</span>
            </p>
          ) : null}
          <p className={`text-lg text-amber-100/95 ${userName ? "mt-1" : "mt-2"}`}>
            {isUser
              ? "Set meal time, start your meal, pick a plate section (1–4), and see your bites."
              : "Pick food, set your meal time, and track bites—step by step."}
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

        {isUser ? (
          <>
            <section aria-labelledby="user-meal-time">
              <h2 id="user-meal-time" className="mb-3 text-center text-2xl font-bold text-amber-100">
                Meal time
              </h2>
              <div className="rounded-2xl border-2 border-stone-600 bg-[#f5ebe0] p-5 shadow-md">
                <label htmlFor="meal-time-user" className="flex items-center justify-center gap-2 text-lg font-bold text-stone-950">
                  <Clock className="h-6 w-6" aria-hidden />
                  Today&apos;s meal time
                </label>
                <Input
                  id="meal-time-user"
                  type="time"
                  value={mealTime}
                  onChange={(e) => setMealTime(e.target.value)}
                  className="mt-4 h-16 rounded-2xl border-2 border-stone-600 bg-[#fffefb] text-center text-3xl font-bold tabular-nums text-stone-950 focus-visible:border-blue-800"
                />
              </div>
            </section>

            <section aria-labelledby="user-controls" className="grid grid-cols-3 gap-3">
              <h2 id="user-controls" className="col-span-3 text-center text-2xl font-bold text-amber-100">
                Session
              </h2>
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
                variant="outline"
                className="h-16 rounded-2xl border-2 border-stone-600 bg-stone-200 text-lg font-semibold text-stone-900 hover:bg-stone-100"
                onClick={pauseSession}
              >
                <Pause className="mr-2 h-6 w-6" />
                Pause
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-16 rounded-2xl border-2 border-stone-600 bg-stone-200 text-lg font-semibold text-stone-900 hover:bg-stone-100"
                onClick={() => void stopSession()}
              >
                <Square className="mr-2 h-6 w-6" />
                Stop
              </Button>
            </section>

            <section aria-labelledby="user-plate">
              <h2 id="user-plate" className="mb-3 text-center text-2xl font-bold text-amber-100">
                Choose food section
              </h2>
              <p className="mb-4 text-center text-lg text-amber-100/90">
                The plate has <strong className="text-white">4 sections</strong>. Tap a number for the next bite.
              </p>
              <div
                className="mx-auto max-w-sm rounded-3xl border-4 border-stone-700 bg-[#e8dcc8] p-3 shadow-inner"
                role="group"
                aria-label="Plate with four numbered sections"
              >
                <div className="grid grid-cols-2 gap-2">
                  {PLATE_SECTIONS.map((sec) => {
                    const active = selectedSection === sec.num;
                    return (
                      <button
                        key={sec.num}
                        type="button"
                        onClick={() => setSelectedSection(sec.num)}
                        className={`flex min-h-[6.5rem] flex-col items-center justify-center rounded-2xl border-4 text-center transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 ${
                          active
                            ? "border-blue-950 bg-blue-900 text-white shadow-lg"
                            : "border-stone-600 bg-[#f5ebe0] text-stone-950 hover:border-stone-800"
                        }`}
                        aria-pressed={active}
                        aria-label={`Section ${sec.num}`}
                      >
                        <span className="text-5xl font-black tabular-nums leading-none">{sec.num}</span>
                        <span className={`mt-1 text-sm font-semibold ${active ? "text-blue-100" : "text-stone-600"}`}>
                          Section {sec.num}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
              <p className="mt-4 text-center text-xl font-bold text-amber-100">
                Selected: section <span className="text-white">{selectedSection}</span>
              </p>
            </section>

            <Button
              type="button"
              className="h-16 w-full rounded-2xl border-2 border-red-900 bg-red-800 text-lg font-bold text-white hover:bg-red-900"
              onClick={() => void emergencyStop()}
            >
              <AlertTriangle className="mr-2 h-6 w-6" />
              Emergency stop
            </Button>

            <div className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] p-6 shadow-lg">
              <p className="text-center text-xl font-bold text-stone-900">Bites: {bitesCompleted}</p>
              <p className="mt-2 text-center text-lg font-medium text-stone-800">{statusText}</p>
            </div>
          </>
        ) : (
          <>
            <section aria-labelledby="food-heading">
              <h2 id="food-heading" className="mb-3 text-center text-2xl font-bold text-amber-100">
                Food for the next bite
              </h2>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {PLATE_SECTIONS.map((food) => {
                  const active = selectedSection === food.num;
                  return (
                    <button
                      key={food.id}
                      type="button"
                      onClick={() => setSelectedSection(food.num)}
                      className={`min-h-[5.5rem] rounded-2xl border-2 px-4 py-4 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 ${
                        active
                          ? "border-blue-950 bg-blue-900 text-white shadow-lg"
                          : "border-stone-600 bg-[#f5ebe0] text-stone-950 hover:border-stone-800"
                      }`}
                    >
                      <span className="block text-lg font-bold text-amber-200">Section {food.num}</span>
                      <span className="block text-2xl font-bold">{food.name}</span>
                      <span
                        className={`mt-1 block text-base font-medium ${active ? "text-blue-100" : "text-stone-800"}`}
                      >
                        {food.hint}
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="mt-4 text-center text-lg text-amber-100">
                Selected:{" "}
                <strong className="font-bold text-white">
                  {selectedMeta.name} (section {selectedSection})
                </strong>
              </p>
            </section>

            <div className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] p-6 shadow-lg">
              <p className="text-center text-xl font-bold text-stone-900">Bites: {bitesCompleted}</p>
              <p className="mt-2 text-center text-lg font-medium text-stone-800">{statusText}</p>
            </div>

            <section className="space-y-4" aria-labelledby="schedule-heading">
              <h2 id="schedule-heading" className="text-center text-2xl font-bold text-amber-100">
                Meal time
              </h2>

              <div className="rounded-2xl border-2 border-stone-600 bg-[#f5ebe0] p-5 shadow-md">
                <label htmlFor="meal-time" className="flex items-center justify-center gap-2 text-lg font-bold text-stone-950">
                  <Clock className="h-6 w-6" aria-hidden />
                  Meal time today
                </label>
                <p className="mb-3 text-center text-base font-medium text-stone-800">
                  When do you plan to eat this meal? (for reminders)
                </p>
                <Input
                  id="meal-time"
                  type="time"
                  value={mealTime}
                  onChange={(e) => setMealTime(e.target.value)}
                  className="h-16 rounded-2xl border-2 border-stone-600 bg-[#fffefb] text-center text-3xl font-bold tabular-nums text-stone-950 focus-visible:border-blue-800"
                />
              </div>
            </section>

            <section aria-labelledby="controls-heading">
              <h2 id="controls-heading" className="mb-3 text-center text-2xl font-bold text-amber-100">
                Controls
              </h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
                  variant="outline"
                  className="h-16 rounded-2xl border-2 border-stone-600 bg-stone-200 text-lg font-semibold text-stone-900 hover:bg-stone-100"
                  onClick={pauseSession}
                >
                  <Pause className="mr-2 h-6 w-6" />
                  Pause
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="h-16 rounded-2xl border-2 border-stone-600 bg-stone-200 text-lg font-semibold text-stone-900 hover:bg-stone-100"
                  onClick={() => void stopSession()}
                >
                  <Square className="mr-2 h-6 w-6" />
                  Stop
                </Button>
              </div>
              <Button
                type="button"
                className="mt-4 h-16 w-full rounded-2xl border-2 border-red-900 bg-red-800 text-lg font-bold text-white hover:bg-red-900"
                onClick={() => void emergencyStop()}
              >
                <AlertTriangle className="mr-2 h-6 w-6" />
                Emergency stop
              </Button>
            </section>

            <section aria-labelledby="history-heading" className="space-y-4">
              <h2 id="history-heading" className="flex items-center justify-center gap-2 text-2xl font-bold text-amber-100">
                <History className="h-7 w-7" aria-hidden />
                User meal history
              </h2>
              <p className="text-center text-base text-amber-100/90">
                {previewMode ? "Saved on this device for " : "Saved in your account for "}
                <strong className="text-white">{userName ?? userEmail ?? "this account"}</strong>.
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
                      No finished meals yet. Press Start to count automatically, then press Stop to save the meal.
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
                          <p className="mt-2 text-sm font-semibold text-stone-600">
                            Planned time: {entry.plannedMealTime ?? "—"} · Bites:{" "}
                            <span className="text-stone-950">{entry.bitesTotal}</span>
                          </p>
                          <p className="mt-2 text-base font-bold text-stone-950">Food by section</p>
                          <ul className="mt-1 grid grid-cols-1 gap-1 sm:grid-cols-2">
                            {PLATE_SECTIONS.map((sec) => {
                              const n = entry.bySection[sec.num];
                              if (n === 0) return null;
                              return (
                                <li key={sec.num} className="flex justify-between rounded-lg bg-stone-100 px-3 py-2 text-sm">
                                  <span>
                                    <span className="font-black text-blue-900">{sec.num}</span> {sec.name}
                                  </span>
                                  <span className="font-bold tabular-nums">{n} bite{n === 1 ? "" : "s"}</span>
                                </li>
                              );
                            })}
                          </ul>
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
