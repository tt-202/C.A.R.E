import {
  saveCareProfile as persistCareProfileLocal,
  type CareProfile,
} from "@/lib/careProfileStorage";
import { normalizeMealSchedule } from "@/lib/mealSchedule";

export type ProfileSaveResult =
  | { ok: true }
  | { ok: false; error: string; status?: number };

async function readProfileError(res: Response): Promise<string> {
  const body = (await res.json().catch(() => ({}))) as { error?: string };
  const detail = body.error?.trim();
  if (detail) return detail;
  if (res.status === 401) return "Session expired — sign out and sign in again.";
  if (res.status === 400) return "Invalid data sent to the server.";
  if (res.status >= 500) return "Server error — check Vercel env (Firebase + database).";
  return `Request failed (${res.status}).`;
}

export function formatProfileSaveError(result: ProfileSaveResult): string {
  if (result.ok) return "";
  if (result.status === 401) {
    return "Could not save reminder times. Sign out and sign in again.";
  }
  if (result.error.includes("FIREBASE_SERVICE_ACCOUNT_JSON")) {
    return "Could not save reminder times. Server Firebase config is missing or invalid (Vercel env).";
  }
  if (result.error.includes("Database") || result.error.includes("meal time columns")) {
    return `Could not save reminder times. ${result.error}`;
  }
  return `Could not save reminder times. ${result.error}`;
}

export async function saveCareProfileToServer(
  getIdToken: () => Promise<string>,
  profile: Pick<
    CareProfile,
    "careRecipientName" | "caregiverName" | "breakfastTime" | "lunchTime" | "dinnerTime"
  >,
): Promise<ProfileSaveResult> {
  const schedule = normalizeMealSchedule(profile);
  try {
    const token = await getIdToken();
    const res = await fetch("/api/profile", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        careRecipientName: profile.careRecipientName,
        caregiverName: profile.caregiverName,
        breakfastTime: schedule.breakfastTime,
        lunchTime: schedule.lunchTime,
        dinnerTime: schedule.dinnerTime,
      }),
    });
    if (res.ok) return { ok: true };
    const error = await readProfileError(res);
    console.warn("[profile] save failed", res.status, error);
    return { ok: false, error, status: res.status };
  } catch (e) {
    console.warn("[profile] save failed", e);
    return {
      ok: false,
      error: "Could not reach the server. Check your internet connection.",
    };
  }
}

export async function saveMealScheduleOnly(
  getIdToken: () => Promise<string>,
  schedule: { breakfastTime: string; lunchTime: string; dinnerTime: string },
  names?: { careRecipientName: string; caregiverName: string },
): Promise<ProfileSaveResult> {
  const normalized = normalizeMealSchedule(schedule);
  try {
    const token = await getIdToken();
    const res = await fetch("/api/profile", {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...normalized,
        ...(names
          ? {
              careRecipientName: names.careRecipientName,
              caregiverName: names.caregiverName,
            }
          : {}),
      }),
    });
    if (res.ok) return { ok: true };
    const error = await readProfileError(res);
    console.warn("[profile] schedule save failed", res.status, error);
    return { ok: false, error, status: res.status };
  } catch (e) {
    console.warn("[profile] schedule save failed", e);
    return {
      ok: false,
      error: "Could not reach the server. Check your internet connection.",
    };
  }
}

export async function saveCareProfile(
  uid: string,
  getIdToken: () => Promise<string>,
  careRecipientName: string,
  caregiverName: string,
): Promise<void> {
  const profile: CareProfile = {
    uid,
    careRecipientName,
    caregiverName,
    ...normalizeMealSchedule(null),
  };
  persistCareProfileLocal(profile);

  try {
    await saveCareProfileToServer(getIdToken, profile);
  } catch {
    console.warn("[profile] server save failed");
  }
}

export async function saveMealSchedule(
  uid: string,
  getIdToken: () => Promise<string>,
  careRecipientName: string,
  caregiverName: string,
  schedule: { breakfastTime: string; lunchTime: string; dinnerTime: string },
): Promise<ProfileSaveResult> {
  const normalized = normalizeMealSchedule(schedule);
  const profile: CareProfile = {
    uid,
    careRecipientName,
    caregiverName,
    ...normalized,
  };
  persistCareProfileLocal(profile);

  const patch = await saveMealScheduleOnly(getIdToken, normalized, {
    careRecipientName,
    caregiverName,
  });
  if (patch.ok) return patch;

  const post = await saveCareProfileToServer(getIdToken, profile);
  if (post.ok) return post;

  return {
    ok: false,
    error: post.error || patch.error,
    status: post.status ?? patch.status,
  };
}
