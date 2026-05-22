"use client";

import { useEffect, useRef } from "react";
import {
  REMINDER_LEAD_MINUTES,
  REMINDER_WINDOW_MINUTES,
} from "@/lib/mealReminderPush";
import { MEAL_SLOTS, type MealSchedule } from "@/lib/mealSchedule";
import { isFcmConfigured } from "@/lib/firebasePublicConfig";
import { triggerMealReminderPush } from "@/lib/fcmRegisterApi";

export { REMINDER_LEAD_MINUTES } from "@/lib/mealReminderPush";

const POLL_MS = 15_000;

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
  getIdToken?: () => Promise<string>;
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
) {
  const name = careRecipientName || "your loved one";
  const title = `C.A.R.E — ${slotLabel} in ${REMINDER_LEAD_MINUTES} min`;
  const body = `${name}'s ${slotLabel.toLowerCase()} is at ${time}. Get ready — ${REMINDER_LEAD_MINUTES} minutes to go.`;

  onReminder?.({ slotKey, title, body });
  showBrowserNotification(title, body, fireKey);
}

export function useMealReminders({
  schedule,
  careRecipientName,
  enabled,
  getIdToken,
  onReminder,
}: Options) {
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
        const remindAt = target - REMINDER_LEAD_MINUTES;
        const fireKey = `${day}:${slot.key}:early`;
        if (firedRef.current[fireKey]) continue;
        if (nowMins < remindAt || nowMins >= remindAt + REMINDER_WINDOW_MINUTES) continue;

        firedRef.current[fireKey] = "1";
        dispatchReminder(
          slot.key,
          slot.label,
          time,
          careRecipientName,
          fireKey,
          onReminder,
        );
        if (isFcmConfigured() && getIdToken) {
          void triggerMealReminderPush(getIdToken, {
            slotKey: slot.key,
            slotLabel: slot.label,
            time,
            careRecipientName,
          });
        }
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
  }, [schedule, careRecipientName, enabled, getIdToken, onReminder]);
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
    "C.A.R.E — Test reminder",
    `Notifications work. You'll get alerts ${REMINDER_LEAD_MINUTES} minutes before ${name}'s meals.`,
    "care-test",
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
