import { MEAL_SLOTS, normalizeMealSchedule, type MealSchedule } from "@/lib/mealSchedule";
import { resolveMealTimezone, zonedClock } from "@/lib/mealReminderTimezone";

/** Notify this many minutes before the scheduled meal time. */
export const REMINDER_LEAD_MINUTES = 60;
/** Matches Vercel cron interval (1 min) with a small buffer. */
export const REMINDER_WINDOW_MINUTES = 6;

function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map((x) => parseInt(x, 10));
  return (h || 0) * 60 + (m || 0);
}

export function mealReminderFireKey(
  slotKey: string,
  day?: string,
  timeZone?: string,
  now = new Date(),
): string {
  const dateKey = day ?? zonedClock(now, resolveMealTimezone(timeZone)).dateKey;
  return `${dateKey}:${slotKey}:early`;
}

export function buildMealReminderPush(
  slotLabel: string,
  time: string,
  careRecipientName: string,
): { title: string; body: string; tag: string } {
  const name = careRecipientName || "your loved one";
  return {
    title: `${name} — ${slotLabel} in 1 hour`,
    body: `Meal time is ${time}. Please get ${name} ready.`,
    tag: `meal-early-${slotLabel.toLowerCase()}`,
  };
}

/** Slots due REMINDER_LEAD_MINUTES before meal time in the care pair's timezone. */
export function dueMealReminderSlots(
  schedule: MealSchedule,
  now = new Date(),
  timeZone?: string,
): Array<{ slotKey: string; slotLabel: string; time: string; fireKey: string }> {
  const normalized = normalizeMealSchedule(schedule);
  const tz = resolveMealTimezone(timeZone);
  const { nowMins, dateKey } = zonedClock(now, tz);
  const due: Array<{ slotKey: string; slotLabel: string; time: string; fireKey: string }> = [];

  for (const slot of MEAL_SLOTS) {
    const time = normalized[slot.field];
    const target = timeToMinutes(time);
    const remindAt = target - REMINDER_LEAD_MINUTES;
    const fireKey = mealReminderFireKey(slot.key, dateKey, tz, now);
    if (nowMins < remindAt || nowMins >= remindAt + REMINDER_WINDOW_MINUTES) continue;
    due.push({ slotKey: slot.key, slotLabel: slot.label, time, fireKey });
  }

  return due;
}
