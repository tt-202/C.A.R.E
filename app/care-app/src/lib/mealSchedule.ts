export type MealSchedule = {
  breakfastTime: string;
  lunchTime: string;
  dinnerTime: string;
};

export const DEFAULT_MEAL_SCHEDULE: MealSchedule = {
  breakfastTime: "08:00",
  lunchTime: "12:30",
  dinnerTime: "18:00",
};

export const MEAL_SLOTS = [
  { key: "breakfast" as const, label: "Breakfast", field: "breakfastTime" as const },
  { key: "lunch" as const, label: "Lunch", field: "lunchTime" as const },
  { key: "dinner" as const, label: "Dinner", field: "dinnerTime" as const },
];

export function normalizeMealSchedule(input?: Partial<MealSchedule> | null): MealSchedule {
  return {
    breakfastTime: input?.breakfastTime?.trim() || DEFAULT_MEAL_SCHEDULE.breakfastTime,
    lunchTime: input?.lunchTime?.trim() || DEFAULT_MEAL_SCHEDULE.lunchTime,
    dinnerTime: input?.dinnerTime?.trim() || DEFAULT_MEAL_SCHEDULE.dinnerTime,
  };
}

function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map((x) => parseInt(x, 10));
  return (h || 0) * 60 + (m || 0);
}

/** Pick the meal slot whose scheduled time is closest to now (for logging). */
export function activeMealSlot(now: Date, schedule: MealSchedule): { label: string; time: string } {
  const nowMins = now.getHours() * 60 + now.getMinutes();
  const slots = MEAL_SLOTS.map((s) => ({
    label: s.label,
    time: schedule[s.field],
    mins: timeToMinutes(schedule[s.field]),
  }));
  let best = slots[0];
  let bestDiff = Math.abs(nowMins - best.mins);
  for (const slot of slots.slice(1)) {
    const diff = Math.abs(nowMins - slot.mins);
    if (diff < bestDiff) {
      best = slot;
      bestDiff = diff;
    }
  }
  return { label: best.label, time: best.time };
}

export function formatPlannedMealTime(label: string, time: string): string {
  return `${label} ${time}`;
}

export function parsePlannedMealLabel(planned: string | undefined | null): string | null {
  if (!planned) return null;
  for (const slot of MEAL_SLOTS) {
    if (planned.startsWith(slot.label)) return slot.label;
  }
  return null;
}

/** First meal slot at or after the current clock time (for starting a new session). */
export function upcomingMealSlot(now: Date, schedule: MealSchedule): { label: string; time: string } {
  const nowMins = now.getHours() * 60 + now.getMinutes();
  for (const slot of MEAL_SLOTS) {
    const mins = timeToMinutes(schedule[slot.field]);
    if (mins >= nowMins) {
      return { label: slot.label, time: schedule[slot.field] };
    }
  }
  return { label: MEAL_SLOTS[0].label, time: schedule[MEAL_SLOTS[0].field] };
}

export type PlannedMealSlot = { label: string; time: string; note?: "tomorrow" };

/** After a meal ends, move to the next slot on the daily schedule. */
export function nextMealSlotAfter(
  completedLabel: string | null,
  schedule: MealSchedule,
  now: Date = new Date(),
): PlannedMealSlot {
  const slots = MEAL_SLOTS.map((s) => ({
    label: s.label,
    time: schedule[s.field],
  }));

  if (completedLabel) {
    const idx = MEAL_SLOTS.findIndex((s) => s.label === completedLabel);
    if (idx >= 0 && idx < MEAL_SLOTS.length - 1) {
      return slots[idx + 1];
    }
    if (idx === MEAL_SLOTS.length - 1) {
      return { ...slots[0], note: "tomorrow" };
    }
  }

  return upcomingMealSlot(now, schedule);
}

export function formatPlannedMealDisplay(slot: PlannedMealSlot): string {
  const base = formatPlannedMealTime(slot.label, slot.time);
  return slot.note === "tomorrow" ? `Tomorrow — ${base}` : base;
}
