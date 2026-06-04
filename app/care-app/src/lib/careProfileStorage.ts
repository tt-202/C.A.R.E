import { DEFAULT_MEAL_SCHEDULE, normalizeMealSchedule, type MealSchedule } from "@/lib/mealSchedule";
import type { UserRole } from "@/AuthPage";

const PROFILE_KEY = "care_profile";

export type CareProfile = {
  /** Shared care pair id (Firestore + alerts). */
  carePairId: string;
  /** Signed-in Firebase account. */
  firebaseUid: string;
  role: UserRole;
  careRecipientName: string;
  caregiverName: string;
  breakfastTime: string;
  lunchTime: string;
  dinnerTime: string;
  linkedUser?: boolean;
  linkedCaregiver?: boolean;
};

/** @deprecated use carePairId — kept for one release of cached profiles. */
export type LegacyCareProfile = CareProfile & { uid?: string };

export function careProfileToSchedule(profile: Pick<CareProfile, "breakfastTime" | "lunchTime" | "dinnerTime">): MealSchedule {
  return normalizeMealSchedule(profile);
}

function normalizeStoredProfile(parsed: LegacyCareProfile, firebaseUid: string): CareProfile | null {
  const carePairId = parsed.carePairId ?? (parsed.uid && parsed.uid !== firebaseUid ? parsed.uid : undefined);
  if (!carePairId) return null;
  const storedFirebaseUid = parsed.firebaseUid ?? (parsed.uid === firebaseUid ? firebaseUid : undefined);
  if (storedFirebaseUid && storedFirebaseUid !== firebaseUid) return null;
  if (!parsed.careRecipientName?.trim() || !parsed.caregiverName?.trim()) return null;
  if (parsed.role !== "caregiver" && parsed.role !== "user") return null;
  return {
    carePairId,
    firebaseUid,
    role: parsed.role,
    careRecipientName: parsed.careRecipientName,
    caregiverName: parsed.caregiverName,
    ...normalizeMealSchedule(parsed),
    linkedUser: parsed.linkedUser,
    linkedCaregiver: parsed.linkedCaregiver,
  };
}

export function loadCareProfile(firebaseUid: string): CareProfile | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LegacyCareProfile;
    return normalizeStoredProfile(parsed, firebaseUid);
  } catch {
    return null;
  }
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

export function clearCareProfileNames() {
  localStorage.removeItem(PROFILE_KEY);
}

export function defaultCareProfile(
  carePairId: string,
  firebaseUid: string,
  role: UserRole,
  careRecipientName: string,
  caregiverName: string,
): CareProfile {
  return {
    carePairId,
    firebaseUid,
    role,
    careRecipientName,
    caregiverName,
    ...DEFAULT_MEAL_SCHEDULE,
  };
}
