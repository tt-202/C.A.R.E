import { MEAL_SLOTS, normalizeMealSchedule, type MealSchedule } from "@/lib/mealSchedule";

/** Notify this many minutes before the scheduled meal time. */
export const REMINDER_LEAD_MINUTES = 15;
export const REMINDER_WINDOW_MINUTES = 3;

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map((x) => parseInt(x, 10));
  return (h || 0) * 60 + (m || 0);
}

export function mealReminderFireKey(slotKey: string, day = todayKey()): string {
  return `${day}:${slotKey}:early`;
}

export function buildMealReminderPush(
  slotLabel: string,
  time: string,
  careRecipientName: string,
): { title: string; body: string; tag: string } {
  const name = careRecipientName || "your loved one";
  return {
    title: `C.A.R.E — ${slotLabel} in ${REMINDER_LEAD_MINUTES} min`,
    body: `${name}'s ${slotLabel.toLowerCase()} is at ${time}. Get ready — ${REMINDER_LEAD_MINUTES} minutes to go.`,
    tag: `meal-early-${slotLabel.toLowerCase()}`,
  };
}

/** Slots that should fire a 15-minute-early push right now (server local clock). */
export function dueMealReminderSlots(
  schedule: MealSchedule,
  now = new Date(),
): Array<{ slotKey: string; slotLabel: string; time: string; fireKey: string }> {
  const normalized = normalizeMealSchedule(schedule);
  const nowMins = now.getHours() * 60 + now.getMinutes();
  const day = todayKey();
  const due: Array<{ slotKey: string; slotLabel: string; time: string; fireKey: string }> = [];

  for (const slot of MEAL_SLOTS) {
    const time = normalized[slot.field];
    const target = timeToMinutes(time);
    const remindAt = target - REMINDER_LEAD_MINUTES;
    const fireKey = mealReminderFireKey(slot.key, day);
    if (nowMins < remindAt || nowMins >= remindAt + REMINDER_WINDOW_MINUTES) continue;
    due.push({ slotKey: slot.key, slotLabel: slot.label, time, fireKey });
  }

  return due;
}
