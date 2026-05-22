"use client";

import { useEffect, useRef } from "react";
import { MEAL_SLOTS, type MealSchedule } from "@/lib/mealSchedule";

const POLL_MS = 15_000;
/** Fire once per meal if we're within this many minutes after the scheduled time. */
const REMINDER_WINDOW_MINUTES = 3;

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map((x) => parseInt(x, 10));
  return (h || 0) * 60 + (m || 0);
}

export type MealReminderPayload = {
  slotKey: string;
  title: string;
  body: string;
};

type Options = {
  schedule: MealSchedule;
  careRecipientName: string;
  enabled: boolean;
  onReminder?: (payload: MealReminderPayload) => void;
};

function dispatchReminder(
  slotKey: string,
  slotLabel: string,
  time: string,
  careRecipientName: string,
  fireKey: string,
  onReminder?: (payload: MealReminderPayload) => void,
) {
  const name = careRecipientName || "your loved one";
  const title = `C.A.R.E — ${slotLabel} time`;
  const body = `It's ${time}. Time for ${name}'s ${slotLabel.toLowerCase()}.`;

  onReminder?.({ slotKey, title, body });

  if (typeof Notification !== "undefined" && Notification.permission === "granted") {
    try {
      new Notification(title, { body, tag: fireKey });
    } catch {
      console.info(`[meal reminder] ${title}: ${body}`);
    }
  } else {
    console.info(`[meal reminder] ${title}: ${body}`);
  }
}

export function useMealReminders({ schedule, careRecipientName, enabled, onReminder }: Options) {
  const firedRef = useRef<Record<string, string>>({});

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    const check = () => {
      const now = new Date();
      const nowMins = now.getHours() * 60 + now.getMinutes();
      const day = todayKey();

      for (const slot of MEAL_SLOTS) {
        const time = schedule[slot.field];
        const target = timeToMinutes(time);
        const fireKey = `${day}:${slot.key}`;
        if (firedRef.current[fireKey]) continue;
        if (nowMins < target || nowMins >= target + REMINDER_WINDOW_MINUTES) continue;

        firedRef.current[fireKey] = "1";
        dispatchReminder(
          slot.key,
          slot.label,
          time,
          careRecipientName,
          fireKey,
          onReminder,
        );
      }
    };

    check();
    const id = window.setInterval(check, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") check();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [schedule, careRecipientName, enabled, onReminder]);
}

export function getNotificationPermission(): NotificationPermission | "unsupported" {
  if (typeof Notification === "undefined") return "unsupported";
  return Notification.permission;
}

export async function requestMealReminderPermission(): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const result = await Notification.requestPermission();
  return result === "granted";
}

export function sendTestMealNotification(careRecipientName: string): boolean {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") {
    return false;
  }
  try {
    new Notification("C.A.R.E — Test reminder", {
      body: `Notifications work. Reminders will alert you for ${careRecipientName || "the user"}'s meals.`,
      tag: "care-test",
    });
    return true;
  } catch {
    return false;
  }
}
