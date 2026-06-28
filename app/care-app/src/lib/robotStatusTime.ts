import type { Timestamp } from "firebase/firestore";

/** How long without a Jetson write before we treat live status as stale on refresh. */
export const ROBOT_STATUS_STALE_MS = 2 * 60 * 1000;

export function parseFirestoreDate(value: unknown): Date | null {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value === "object" && value !== null && "toDate" in value) {
    const ts = value as Timestamp;
    if (typeof ts.toDate === "function") return ts.toDate();
  }
  if (typeof value === "object" && value !== null && "seconds" in value) {
    const seconds = (value as { seconds?: number }).seconds;
    if (typeof seconds === "number") return new Date(seconds * 1000);
  }
  if (typeof value === "object" && value !== null && "_seconds" in value) {
    const seconds = (value as { _seconds?: number })._seconds;
    if (typeof seconds === "number") return new Date(seconds * 1000);
  }
  return null;
}

export function isRobotStatusFresh(
  updatedAt: unknown,
  maxAgeMs: number = ROBOT_STATUS_STALE_MS,
): boolean {
  const date = parseFirestoreDate(updatedAt);
  if (!date) return false;
  return Date.now() - date.getTime() <= maxAgeMs;
}

export function formatRobotStatusAge(updatedAt: unknown): string {
  const date = parseFirestoreDate(updatedAt);
  if (!date) return "unknown";
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}
