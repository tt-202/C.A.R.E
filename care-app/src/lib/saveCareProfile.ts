import {
  saveCareProfile as persistCareProfileLocal,
  type CareProfile,
} from "@/lib/careProfileStorage";
import { normalizeMealSchedule } from "@/lib/mealSchedule";

export async function saveCareProfileToServer(
  getIdToken: () => Promise<string>,
  profile: Pick<
    CareProfile,
    "careRecipientName" | "caregiverName" | "breakfastTime" | "lunchTime" | "dinnerTime"
  >,
): Promise<boolean> {
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
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      console.warn("[profile] save failed", res.status, body.error ?? res.statusText);
    }
    return res.ok;
  } catch (e) {
    console.warn("[profile] save failed", e);
    return false;
  }
}

export async function saveMealScheduleOnly(
  getIdToken: () => Promise<string>,
  schedule: { breakfastTime: string; lunchTime: string; dinnerTime: string },
): Promise<boolean> {
  const normalized = normalizeMealSchedule(schedule);
  try {
    const token = await getIdToken();
    const res = await fetch("/api/profile", {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(normalized),
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      console.warn("[profile] schedule save failed", res.status, body.error ?? res.statusText);
    }
    return res.ok;
  } catch (e) {
    console.warn("[profile] schedule save failed", e);
    return false;
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
): Promise<boolean> {
  const normalized = normalizeMealSchedule(schedule);
  const profile: CareProfile = {
    uid,
    careRecipientName,
    caregiverName,
    ...normalized,
  };
  persistCareProfileLocal(profile);
  const patchOk = await saveMealScheduleOnly(getIdToken, normalized);
  if (patchOk) return true;
  return saveCareProfileToServer(getIdToken, profile);
}
