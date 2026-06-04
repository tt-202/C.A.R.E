import {
  saveCareProfile as persistCareProfileLocal,
  type CareProfile,
} from "@/lib/careProfileStorage";
import type { UserRole } from "@/AuthPage";
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
  if (result.error.includes("Database") || result.error.includes("care pair")) {
    return `Could not save reminder times. ${result.error}`;
  }
  return `Could not save reminder times. ${result.error}`;
}

function profileFromResponse(
  firebaseUid: string,
  data: Record<string, unknown>,
): CareProfile | null {
  if (!data.linked || typeof data.carePairId !== "string" || typeof data.role !== "string") {
    return null;
  }
  if (data.role !== "caregiver" && data.role !== "user") return null;
  const schedule = normalizeMealSchedule(data);
  return {
    carePairId: data.carePairId,
    firebaseUid,
    role: data.role as UserRole,
    careRecipientName: String(data.careRecipientName ?? ""),
    caregiverName: String(data.caregiverName ?? ""),
    ...schedule,
    linkedUser: Boolean(data.linkedUser),
    linkedCaregiver: Boolean(data.linkedCaregiver),
  };
}

export async function loadProfileFromServer(
  firebaseUid: string,
  getIdToken: () => Promise<string>,
): Promise<CareProfile | null> {
  try {
    const token = await getIdToken();
    const res = await fetch("/api/profile", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as Record<string, unknown>;
    const profile = profileFromResponse(firebaseUid, data);
    if (profile) persistCareProfileLocal(profile);
    return profile;
  } catch {
    return null;
  }
}

export async function saveCareProfileToServer(
  getIdToken: () => Promise<string>,
  profile: Pick<
    CareProfile,
    "careRecipientName" | "caregiverName" | "breakfastTime" | "lunchTime" | "dinnerTime"
  >,
  firebaseUid: string,
): Promise<ProfileSaveResult & { profile?: CareProfile }> {
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
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.ok) {
      const saved = profileFromResponse(firebaseUid, data);
      return saved ? { ok: true, profile: saved } : { ok: true };
    }
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

export async function acceptInviteCode(
  getIdToken: () => Promise<string>,
  code: string,
  firebaseUid: string,
): Promise<{ ok: true; profile: CareProfile } | { ok: false; error: string }> {
  try {
    const token = await getIdToken();
    const res = await fetch("/api/invites/accept", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code: code.trim().toUpperCase() }),
    });
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) {
      return { ok: false, error: String(data.error ?? "Could not accept invite") };
    }
    const profile = profileFromResponse(firebaseUid, data);
    if (!profile) {
      return { ok: false, error: "Invalid profile returned from server" };
    }
    persistCareProfileLocal(profile);
    return { ok: true, profile };
  } catch {
    return { ok: false, error: "Could not reach the server." };
  }
}

export async function createCarePairProfile(
  firebaseUid: string,
  getIdToken: () => Promise<string>,
  role: UserRole,
  careRecipientName: string,
  caregiverName: string,
): Promise<CareProfile | null> {
  const result = await saveCareProfileToServer(
    getIdToken,
    {
      careRecipientName,
      caregiverName,
      ...normalizeMealSchedule(null),
    },
    firebaseUid,
  );
  if (!result.ok || !result.profile) return null;
  const profile: CareProfile = { ...result.profile, firebaseUid, role };
  persistCareProfileLocal(profile);
  return profile;
}

export async function saveCareProfile(
  firebaseUid: string,
  getIdToken: () => Promise<string>,
  role: UserRole,
  careRecipientName: string,
  caregiverName: string,
): Promise<CareProfile | null> {
  return createCarePairProfile(firebaseUid, getIdToken, role, careRecipientName, caregiverName);
}

export async function saveMealSchedule(
  firebaseUid: string,
  getIdToken: () => Promise<string>,
  careRecipientName: string,
  caregiverName: string,
  schedule: { breakfastTime: string; lunchTime: string; dinnerTime: string },
  role: UserRole,
  carePairId: string,
): Promise<ProfileSaveResult> {
  const normalized = normalizeMealSchedule(schedule);
  const profile: CareProfile = {
    carePairId,
    firebaseUid,
    role,
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

  const post = await saveCareProfileToServer(getIdToken, profile, firebaseUid);
  if (post.ok) return post;

  return {
    ok: false,
    error: post.error || patch.error,
    status: post.status ?? patch.status,
  };
}

export async function createUserInvite(
  getIdToken: () => Promise<string>,
): Promise<{ ok: true; code: string; expiresAt: string } | { ok: false; error: string }> {
  try {
    const token = await getIdToken();
    const res = await fetch("/api/invites", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ role: "user" }),
    });
    const data = (await res.json().catch(() => ({}))) as {
      code?: string;
      expiresAt?: string;
      error?: string;
    };
    if (!res.ok || !data.code) {
      return { ok: false, error: data.error ?? "Could not create invite" };
    }
    return { ok: true, code: data.code, expiresAt: data.expiresAt ?? "" };
  } catch {
    return { ok: false, error: "Could not reach the server." };
  }
}
