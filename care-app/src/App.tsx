"use client";

import { useCallback, useEffect, useState } from "react";
import { onAuthStateChanged, signOut, type User } from "firebase/auth";
import AuthPage from "./AuthPage";
import CareFeedingApp from "./CareFeedingApp";
import RoleSelectPage from "./RoleSelectPage";
import type { UserRole } from "./AuthPage";
import { getClientAuth } from "@/lib/firebaseClient";
import {
  clearCareProfileNames,
  loadCareProfile,
  saveCareProfile,
  type CareProfile,
} from "@/lib/careProfileStorage";
import { normalizeMealSchedule } from "@/lib/mealSchedule";

const ROLE_KEY = "care_role";

function loadRole(uid: string): UserRole | undefined {
  try {
    const raw = localStorage.getItem(ROLE_KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as { uid?: string; role?: UserRole };
    if (parsed.uid === uid && (parsed.role === "caregiver" || parsed.role === "user")) {
      return parsed.role;
    }
  } catch {
    /* ignore */
  }
  return undefined;
}

function saveRole(uid: string, role: UserRole) {
  localStorage.setItem(ROLE_KEY, JSON.stringify({ uid, role }));
}

function clearRoleStorage() {
  localStorage.removeItem(ROLE_KEY);
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<UserRole | undefined>(undefined);
  const [authReady, setAuthReady] = useState(false);
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
        setRole(loadRole(u.uid));
      } else {
        setRole(undefined);
        clearRoleStorage();
        setCareProfile(null);
        clearCareProfileNames();
      }
      setAuthReady(true);
    });
    return () => unsub();
  }, []);

  useEffect(() => {
    if (!user) return;
    const cached = loadCareProfile(user.uid);
    if (cached) setCareProfile(cached);

    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/profile", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as Partial<CareProfile>;
        if (cancelled) return;
        if (data.careRecipientName && data.caregiverName) {
          const schedule = normalizeMealSchedule(data);
          const next: CareProfile = {
            uid: user.uid,
            careRecipientName: data.careRecipientName,
            caregiverName: data.caregiverName,
            ...schedule,
          };
          setCareProfile(next);
          saveCareProfile(next);
        }
      } catch {
        /* keep cached profile */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const getIdToken = useCallback(async () => {
    if (!user) throw new Error("Not signed in");
    return user.getIdToken();
  }, [user]);

  const handleSignOut = async () => {
    clearRoleStorage();
    clearCareProfileNames();
    try {
      const auth = getClientAuth();
      await signOut(auth);
    } catch {
      /* still clear UI if Firebase sign-out fails */
    }
    setUser(null);
    setRole(undefined);
    setCareProfile(null);
  };

  if (!authReady) {
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
          onSignedIn={(u) => {
            setUser(u);
            setRole(loadRole(u.uid));
          }}
        />
      </div>
    );
  }

  const email = user.email ?? "";
  const careRecipientName =
    careProfile?.careRecipientName ?? user.displayName ?? user.email?.split("@")[0] ?? "User";
  const caregiverName =
    careProfile?.caregiverName ?? user.displayName ?? user.email?.split("@")[0] ?? "Caregiver";

  return (
    <div className="care-app-shell">
      {!role ? (
        <RoleSelectPage
          careRecipientName={careRecipientName}
          caregiverName={caregiverName}
          onChooseRole={(next) => {
            saveRole(user.uid, next);
            setRole(next);
          }}
          onSignOut={handleSignOut}
        />
      ) : (
        <CareFeedingApp
          role={role}
          careRecipientName={careRecipientName}
          caregiverName={caregiverName}
          userEmail={email}
          profileUid={user.uid}
          initialMealSchedule={normalizeMealSchedule(careProfile)}
          onMealScheduleSaved={(schedule) => {
            setCareProfile((prev) =>
              prev
                ? { ...prev, ...schedule }
                : {
                    uid: user.uid,
                    careRecipientName,
                    caregiverName,
                    ...schedule,
                  },
            );
          }}
          getIdToken={getIdToken}
          onRoleChange={(nextRole) => {
            saveRole(user.uid, nextRole);
            setRole(nextRole);
          }}
          onSignOut={handleSignOut}
        />
      )}
    </div>
  );
}
