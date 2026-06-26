"use client";

import { useEffect, useRef } from "react";
import {
  REMINDER_LEAD_MINUTES,
  dueMealReminderSlots,
} from "@/lib/mealReminderPush";
import { detectBrowserTimezone } from "@/lib/mealReminderTimezone";
import type { MealSchedule } from "@/lib/mealSchedule";
import { isFcmConfigured } from "@/lib/firebasePublicConfig";
import {
  isScheduledNotificationSupported,
  scheduleLocalMealReminders,
} from "@/lib/scheduleLocalMealReminders";

export { REMINDER_LEAD_MINUTES } from "@/lib/mealReminderPush";

const POLL_MS = 15_000;

export type MealReminderPayload = {
  slotKey: string;
  title: string;
  body: string;
};

type Options = {
  schedule: MealSchedule;
  careRecipientName: string;
  enabled: boolean;
  timezone?: string;
  onReminder?: (payload: MealReminderPayload) => void;
};

export function showBrowserNotification(
  title: string,
  body: string,
  tag: string,
): boolean {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") {
    return false;
  }
  try {
    new Notification(title, { body, tag });
    return true;
  } catch {
    console.info(`[notification] ${title}: ${body}`);
    return false;
  }
}

function dispatchReminder(
  slotKey: string,
  slotLabel: string,
  time: string,
  careRecipientName: string,
  fireKey: string,
  onReminder?: (payload: MealReminderPayload) => void,
  options?: { osNotification?: boolean },
) {
  const name = careRecipientName || "your loved one";
  const title = `${name} — ${slotLabel} soon`;
  const body = `Meal time is ${time}. Please get ${name} ready.`;

  onReminder?.({ slotKey, title, body });
  if (options?.osNotification !== false) {
    showBrowserNotification(title, body, fireKey);
  }
}

export function useMealReminders({
  schedule,
  careRecipientName,
  enabled,
  timezone,
  onReminder,
}: Options) {
  const firedRef = useRef<Record<string, string>>({});
  const tz = timezone ?? detectBrowserTimezone();

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    // FCM + server cron is the single delivery path for meal reminders.
    if (isFcmConfigured()) return;

    const scheduledSupported = isScheduledNotificationSupported();
    if (Notification.permission === "granted" && scheduledSupported) {
      void scheduleLocalMealReminders(schedule, careRecipientName, tz);
    }

    // Without scheduled SW notifications, poll for in-app + OS fallback.
    if (scheduledSupported) return;

    const check = () => {
      const due = dueMealReminderSlots(schedule, new Date(), tz);
      for (const slot of due) {
        if (firedRef.current[slot.fireKey]) continue;
        firedRef.current[slot.fireKey] = "1";
        const osNotification = document.visibilityState !== "visible";
        dispatchReminder(
          slot.slotKey,
          slot.slotLabel,
          slot.time,
          careRecipientName,
          slot.fireKey,
          onReminder,
          { osNotification },
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
  }, [schedule, careRecipientName, enabled, onReminder, tz]);
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
  const name = careRecipientName || "the user";
  return showBrowserNotification(
    "C.A.R.E — Friendly reminder",
    `You'll get alerts ${REMINDER_LEAD_MINUTES} minutes before ${name}'s meals.`,
    "care-friendlyreminder",
  );
}

/** User-facing steps when the browser has blocked Notification.permission. */
export function notificationBlockedHelp(): string {
  const host =
    typeof window !== "undefined" ? window.location.hostname : "this site";
  const isLocal = host === "localhost" || host === "127.0.0.1";

  if (isLocal) {
    return (
      "Notifications are blocked for localhost. In Chrome: click the icon left of the address bar " +
      "(tune or lock) → Site settings → Notifications → Allow, then reload this page. " +
      "In Safari: Safari → Settings → Websites → Notifications → select localhost → Allow, then reload. " +
      "On Mac, also check System Settings → Notifications → your browser → allow alerts."
    );
  }

  return (
    `Notifications are blocked for ${host}. Open your browser’s site settings for this page, ` +
    "set Notifications to Allow, reload, then tap Test notification again."
  );
}

export function buildTestReminderPayload(careRecipientName: string): MealReminderPayload {
  const name = careRecipientName || "the user";
  return {
    slotKey: "test",
    title: "C.A.R.E — Test reminder",
    body: `Test OK. You'll get alerts ${REMINDER_LEAD_MINUTES} minutes before ${name}'s meals (yellow banner here + phone banner if allowed).`,
  };
}
