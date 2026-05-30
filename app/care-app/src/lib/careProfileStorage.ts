import { DEFAULT_MEAL_SCHEDULE, normalizeMealSchedule, type MealSchedule } from "@/lib/mealSchedule";

const PROFILE_KEY = "care_profile";

export type CareProfile = {
  uid: string;
  careRecipientName: string;
  caregiverName: string;
  breakfastTime: string;
  lunchTime: string;
  dinnerTime: string;
};

export function careProfileToSchedule(profile: Pick<CareProfile, "breakfastTime" | "lunchTime" | "dinnerTime">): MealSchedule {
  return normalizeMealSchedule(profile);
}

export function loadCareProfile(uid: string): CareProfile | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CareProfile;
    if (parsed.uid !== uid) return null;
    if (!parsed.careRecipientName?.trim() || !parsed.caregiverName?.trim()) return null;
    return {
      ...parsed,
      ...normalizeMealSchedule(parsed),
    };
  } catch {
    return null;
  }
}

/** @deprecated use loadCareProfile */
export function loadCareProfileNames(uid: string): CareProfile | null {
  return loadCareProfile(uid);
}

export function saveCareProfile(profile: CareProfile) {
  localStorage.setItem(
    PROFILE_KEY,
    JSON.stringify({
      ...profile,
      ...normalizeMealSchedule(profile),
    }),
  );
}

/** @deprecated use saveCareProfile */
export function saveCareProfileNames(profile: CareProfile) {
  saveCareProfile(profile);
}

export function clearCareProfileNames() {
  localStorage.removeItem(PROFILE_KEY);
}

export function defaultCareProfile(uid: string, careRecipientName: string, caregiverName: string): CareProfile {
  return {
    uid,
    careRecipientName,
    caregiverName,
    ...DEFAULT_MEAL_SCHEDULE,
  };
}
