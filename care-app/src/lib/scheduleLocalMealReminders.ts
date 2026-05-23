"use client";

import {
  buildMealReminderPush,
  mealReminderFireKey,
  REMINDER_LEAD_MINUTES,
} from "@/lib/mealReminderPush";
import { MEAL_SLOTS, type MealSchedule } from "@/lib/mealSchedule";
import { registerFcmServiceWorker } from "@/lib/firebaseMessagingClient";

function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map((x) => parseInt(x, 10));
  return (h || 0) * 5 + (m || 0);
}

/** Chrome / Edge: schedule OS notifications via the service worker (works when the tab is closed). */
export function isScheduledNotificationSupported(): boolean {
  if (typeof window === "undefined") return false;
  return "TimestampTrigger" in globalThis && "showTrigger" in Notification.prototype;
}

export type ScheduleLocalResult = {
  scheduled: number;
  supported: boolean;
};

/**
 * Schedules one notification per meal slot today, REMINDER_LEAD_MINUTES before meal time.
 * Complements server FCM cron for when the browser tab is closed.
 */
export async function scheduleLocalMealReminders(
  schedule: MealSchedule,
  careRecipientName: string,
): Promise<ScheduleLocalResult> {
  if (typeof window === "undefined" || Notification.permission !== "granted") {
    return { scheduled: 0, supported: false };
  }
  if (!isScheduledNotificationSupported()) {
    return { scheduled: 0, supported: false };
  }

  const sw = await registerFcmServiceWorker();
  if (!sw) return { scheduled: 0, supported: false };

  await navigator.serviceWorker.ready;

  const existing = await sw.getNotifications();
  for (const n of existing) {
    if (n.tag?.startsWith("meal-early-")) n.close();
  }

  const now = new Date();
  const nowMs = now.getTime();
  let scheduled = 0;

  for (const slot of MEAL_SLOTS) {
    const time = schedule[slot.field];
    const [h, m] = time.split(":").map((x) => parseInt(x, 10));
    const mealAt = new Date(now);
    mealAt.setHours(h || 0, m || 0, 0, 0);
    const remindAtMs = mealAt.getTime() - REMINDER_LEAD_MINUTES * 60 * 1000;
    if (remindAtMs <= nowMs) continue;

    const { title, body, tag } = buildMealReminderPush(
      slot.label,
      time,
      careRecipientName,
    );
    const TimestampTriggerCtor = (
      globalThis as unknown as { TimestampTrigger: new (ts: number) => unknown }
    ).TimestampTrigger;

    await sw.showNotification(title, {
      body,
      tag,
      data: { fireKey: mealReminderFireKey(slot.key), link: "/" },
      showTrigger: new TimestampTriggerCtor(remindAtMs),
    } as NotificationOptions);
    scheduled += 1;
  }

  return { scheduled, supported: true };
}

/** Minutes until the next 15-min-early reminder. */
export function minutesUntilNextReminder(schedule: MealSchedule, now = new Date()): number | null {
  const nowMins = now.getHours() * 60 + now.getMinutes();
  let best: number | null = null;

  for (const slot of MEAL_SLOTS) {
    const target = timeToMinutes(schedule[slot.field]);
    const remindAt = target - REMINDER_LEAD_MINUTES;
    if (nowMins < remindAt) {
      const delta = remindAt - nowMins;
      if (best === null || delta < best) best = delta;
    }
  }

  return best;
}
