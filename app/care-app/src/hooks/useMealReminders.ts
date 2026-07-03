"use client";

import { useEffect } from "react";
import {
  REMINDER_LEAD_MINUTES,
  dueMealReminderSlots,
} from "@/lib/mealReminderPush";
import { detectBrowserTimezone } from "@/lib/mealReminderTimezone";
import type { MealSchedule } from "@/lib/mealSchedule";
import { isFcmConfigured } from "@/lib/firebasePublicConfig";
import {
  markMealReminderShownLocally,
  wasMealReminderShownLocally,
} from "@/lib/mealReminderLocalDedup";
import {
  isScheduledNotificationSupported,
  scheduleLocalMealReminders,
} from "@/lib/scheduleLocalMealReminders";

export { REMINDER_LEAD_MINUTES } from "@/lib/mealReminderPush";

const POLL_MS = 60_000;

export type MealReminderPayload = {
  slotKey: string;
  fireKey: string;
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

function dispatchInAppReminder(
  slot: { slotKey: string; slotLabel: string; time: string; fireKey: string },
  careRecipientName: string,
  onReminder?: (payload: MealReminderPayload) => void,
) {
  const name = careRecipientName || "your loved one";
  const title = `${name} — ${slot.slotLabel} in 1 hour`;
  const body = `Meal time is ${slot.time}. Please get ${name} ready.`;
  onReminder?.({
    slotKey: slot.slotKey,
    fireKey: slot.fireKey,
    title,
    body,
  });
}

/**
 * Meal reminders: exactly once per meal slot per day, 1 hour before meal time.
 * - FCM + EasyCron: server push only (no client poll / no local OS schedule).
 * - No FCM: service-worker schedule for OS popup when tab closed; in-app banner when tab open.
 */
export function useMealReminders({
  schedule,
  careRecipientName,
  enabled,
  timezone,
  onReminder,
}: Options) {
  const tz = timezone ?? detectBrowserTimezone();

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    const fcmActive = isFcmConfigured();
    const scheduledSupported = isScheduledNotificationSupported();

    if (!fcmActive && Notification.permission === "granted" && scheduledSupported) {
      void scheduleLocalMealReminders(schedule, careRecipientName, tz);
    }

    if (fcmActive) return;

    const check = () => {
      if (document.visibilityState !== "visible") return;
      const due = dueMealReminderSlots(schedule, new Date(), tz);
      for (const slot of due) {
        if (wasMealReminderShownLocally(slot.fireKey)) continue;
        markMealReminderShownLocally(slot.fireKey);
        dispatchInAppReminder(slot, careRecipientName, onReminder);
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
    `You'll get one alert ${REMINDER_LEAD_MINUTES} minutes before each of ${name}'s meals.`,
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
    "set Notifications to Allow, reload, then tap Save reminder times again."
  );
}

export function buildTestReminderPayload(careRecipientName: string): MealReminderPayload {
  const name = careRecipientName || "the user";
  return {
    slotKey: "test",
    fireKey: "test:early",
    title: "C.A.R.E — Test reminder",
    body: `Test OK. You'll get one alert ${REMINDER_LEAD_MINUTES} minutes before each of ${name}'s meals.`,
  };
}
