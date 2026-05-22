"use client";

import { useEffect, useRef } from "react";
import { MEAL_SLOTS, type MealSchedule } from "@/lib/mealSchedule";

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function timeToMinutes(time: string): number {
  const [h, m] = time.split(":").map((x) => parseInt(x, 10));
  return (h || 0) * 60 + (m || 0);
}

type Options = {
  schedule: MealSchedule;
  careRecipientName: string;
  enabled: boolean;
};

export function useMealReminders({ schedule, careRecipientName, enabled }: Options) {
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
        if (nowMins !== target) continue;

        firedRef.current[fireKey] = "1";
        const name = careRecipientName || "your loved one";
        const title = `C.A.R.E — ${slot.label} time`;
        const body = `It's ${time}. Time for ${name}'s ${slot.label.toLowerCase()}.`;

        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          new Notification(title, { body, tag: fireKey });
        } else {
          console.info(`[meal reminder] ${title}: ${body}`);
        }
      }
    };

    check();
    const id = window.setInterval(check, 30_000);
    return () => window.clearInterval(id);
  }, [schedule, careRecipientName, enabled]);
}

export async function requestMealReminderPermission(): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const result = await Notification.requestPermission();
  return result === "granted";
}
