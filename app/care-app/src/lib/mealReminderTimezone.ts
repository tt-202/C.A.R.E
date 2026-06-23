/** Fallback when a care pair has no timezone saved (US Eastern). */
export const DEFAULT_MEAL_TIMEZONE = "America/New_York";

export function detectBrowserTimezone(): string {
  if (typeof Intl === "undefined") return DEFAULT_MEAL_TIMEZONE;
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || DEFAULT_MEAL_TIMEZONE;
  } catch {
    return DEFAULT_MEAL_TIMEZONE;
  }
}

export function isValidTimezone(tz: string): boolean {
  try {
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

export function resolveMealTimezone(raw?: string | null): string {
  const trimmed = raw?.trim();
  if (trimmed && isValidTimezone(trimmed)) return trimmed;
  const fromEnv = process.env.CARE_DEFAULT_TIMEZONE?.trim();
  if (fromEnv && isValidTimezone(fromEnv)) return fromEnv;
  return DEFAULT_MEAL_TIMEZONE;
}

export type ZonedClock = {
  dateKey: string;
  hours: number;
  minutes: number;
  nowMins: number;
};

/** Local calendar date + clock for meal-time comparisons (not server UTC). */
export function zonedClock(now: Date, timeZone: string): ZonedClock {
  const tz = resolveMealTimezone(timeZone);
  const dtf = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const parts = Object.fromEntries(dtf.formatToParts(now).map((p) => [p.type, p.value]));
  const hours = parseInt(parts.hour ?? "0", 10);
  const minutes = parseInt(parts.minute ?? "0", 10);
  return {
    dateKey: `${parts.year}-${parts.month}-${parts.day}`,
    hours,
    minutes,
    nowMins: hours * 60 + minutes,
  };
}
