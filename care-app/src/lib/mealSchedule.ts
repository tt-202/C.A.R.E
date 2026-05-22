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
