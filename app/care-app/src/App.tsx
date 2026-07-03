"use client";

import { useCallback, useEffect, useState } from "react";
import { onAuthStateChanged, signOut, type User } from "firebase/auth";
import AuthPage from "./AuthPage";
import CareFeedingApp from "./CareFeedingApp";
import type { UserRole } from "./AuthPage";
import { getClientAuth } from "@/lib/firebaseClient";
import {
  clearCareProfileNames,
  loadCareProfile,
  saveCareProfile as persistCareProfileLocal,
  type CareProfile,
} from "@/lib/careProfileStorage";
import { normalizeMealSchedule } from "@/lib/mealSchedule";
import { normalizeBiteHoldSeconds } from "@/lib/biteHoldConfig";
import { resolveMealTimezone } from "@/lib/mealReminderTimezone";
import { loadProfileFromServer } from "@/lib/saveCareProfile";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [careProfile, setCareProfile] = useState<CareProfile | null>(() => {
    try {
      const auth = getClientAuth();
      const currentUser = auth.currentUser;
      if (!currentUser) return null;
      return loadCareProfile(currentUser.uid);
    } catch {
      return null;
    }
  });
  const [authReady, setAuthReady] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);

  const refreshProfile = useCallback(async (u: User) => {
    setProfileLoading(true);
    try {
      const profile = await loadProfileFromServer(u.uid, () => u.getIdToken());
      if (profile) {
        setCareProfile(profile);
      } else {
        setCareProfile(loadCareProfile(u.uid));
      }
    } catch {
      setCareProfile(loadCareProfile(u.uid));
    } finally {
      setProfileLoading(false);
    }
  }, []);

  useEffect(() => {
    let auth;
    try {
      auth = getClientAuth();
    } catch {
      queueMicrotask(() => setAuthReady(true));
      return;
    }
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u);
      if (u) {
        setCareProfile(loadCareProfile(u.uid));
        void refreshProfile(u);
      } else {
        setCareProfile(null);
        clearCareProfileNames();
      }
      setAuthReady(true);
    });
    return () => unsub();
  }, [refreshProfile]);

  const getIdToken = useCallback(async () => {
    if (!user) throw new Error("Not signed in");
    return user.getIdToken();
  }, [user]);

  const handleSignOut = async () => {
    clearCareProfileNames();
    try {
      const auth = getClientAuth();
      await signOut(auth);
    } catch {
      /* still clear UI if Firebase sign-out fails */
    }
    setUser(null);
    setCareProfile(null);
  };

  const handleProfileReady = (profile: CareProfile) => {
    persistCareProfileLocal(profile);
    setCareProfile(profile);
  };

  if (!authReady || (user && profileLoading && !careProfile)) {
    return (
      <div className="care-app-shell flex min-h-screen items-center justify-center text-xl text-white">
        Loading…
      </div>
    );
  }

  if (!user) {
    return (
      <div className="care-app-shell">
        <AuthPage
          onSignedIn={(u, profile) => {
            setUser(u);
            if (profile) {
              handleProfileReady(profile);
            } else {
              void refreshProfile(u);
            }
          }}
        />
      </div>
    );
  }

  if (!careProfile) {
    return (
      <div className="care-app-shell">
        <AuthPage
          initialMode="setup"
          existingUser={user}
          onSignedIn={(u, profile) => {
            setUser(u);
            if (profile) handleProfileReady(profile);
          }}
          onSignOut={handleSignOut}
        />
      </div>
    );
  }

  const role: UserRole = careProfile.role;
  const email = user.email ?? "";
  const carePairId = careProfile.carePairId;
  const allowRoleSwitch = !careProfile.linkedUser;

  return (
    <div className="care-app-shell">
      <CareFeedingApp
        role={role}
        careRecipientName={careProfile.careRecipientName}
        caregiverName={careProfile.caregiverName}
        userEmail={email}
        firebaseUid={user.uid}
        profileUid={carePairId}
        linkedUser={Boolean(careProfile.linkedUser)}
        initialMealSchedule={normalizeMealSchedule(careProfile)}
        initialMealTimezone={resolveMealTimezone(careProfile.timezone)}
        initialBiteHoldSeconds={normalizeBiteHoldSeconds(careProfile.biteHoldSeconds)}
        onMealScheduleSaved={(schedule) => {
          setCareProfile((prev) => (prev ? { ...prev, ...schedule } : prev));
        }}
        onBiteHoldSaved={(seconds) => {
          setCareProfile((prev) => (prev ? { ...prev, biteHoldSeconds: seconds } : prev));
        }}
        getIdToken={getIdToken}
        onRoleChange={
          allowRoleSwitch
            ? (nextRole) => {
                setCareProfile((prev) => (prev ? { ...prev, role: nextRole } : prev));
              }
            : undefined
        }
        onSignOut={handleSignOut}
      />
    </div>
  );
}
