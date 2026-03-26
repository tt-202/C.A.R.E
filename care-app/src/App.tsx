"use client";

import { useCallback, useEffect, useState } from "react";
import { onAuthStateChanged, signOut, type User } from "firebase/auth";
import AuthPage from "./AuthPage";
import CareFeedingApp from "./CareFeedingApp";
import RoleSelectPage from "./RoleSelectPage";
import type { UserRole } from "./AuthPage";
import { getClientAuth } from "@/lib/firebaseClient";

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
      }
      setAuthReady(true);
    });
    return () => unsub();
  }, []);

  const getIdToken = useCallback(async () => {
    if (!user) throw new Error("Not signed in");
    return user.getIdToken();
  }, [user]);

  const handleSignOut = async () => {
    try {
      const auth = getClientAuth();
      await signOut(auth);
    } catch {
      /* ignore */
    }
    clearRoleStorage();
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
        <AuthPage />
      </div>
    );
  }

  const displayName = user.displayName ?? user.email?.split("@")[0] ?? "User";
  const email = user.email ?? "";

  return (
    <div className="care-app-shell">
      {!role ? (
        <RoleSelectPage
          userName={displayName}
          onChooseRole={(next) => {
            saveRole(user.uid, next);
            setRole(next);
          }}
          onSignOut={handleSignOut}
        />
      ) : (
        <CareFeedingApp
          role={role}
          userName={displayName}
          userEmail={email}
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
