const recent = new Map<string, number>();

/** Drop duplicate in-app alerts within a short window (e.g. FCM + Firestore). */
export function shouldDeliverInAppAlert(key: string, windowMs = 30_000): boolean {
  const now = Date.now();
  const last = recent.get(key);
  if (last !== undefined && now - last < windowMs) return false;
  recent.set(key, now);
  return true;
}

export function inAppAlertKey(parts: {
  title?: string;
  body: string;
  alertType?: string;
}): string {
  return `${parts.alertType ?? ""}|${parts.title ?? ""}|${parts.body}`;
}
