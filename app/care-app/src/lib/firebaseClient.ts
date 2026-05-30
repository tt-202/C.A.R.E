"use client";

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

/** Shared across possible duplicate module instances from the bundler (fixes post-login UI not updating). */
const GLOBAL_AUTH_KEY = "__CARE_FIREBASE_AUTH__" as const;

let app: FirebaseApp | undefined;
let auth: Auth | undefined;
let firestore: Firestore | undefined;

function getGlobalAuth(): Auth | undefined {
  if (typeof globalThis === "undefined") return undefined;
  return (globalThis as Record<string, unknown>)[GLOBAL_AUTH_KEY] as Auth | undefined;
}

function setGlobalAuth(next: Auth): void {
  (globalThis as Record<string, unknown>)[GLOBAL_AUTH_KEY] = next;
}

/** True when the minimum Firebase web env vars are set (you can run real sign-in). */
export function isFirebaseConfigured(): boolean {
  return Boolean(
    process.env.NEXT_PUBLIC_FIREBASE_API_KEY &&
      process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN &&
      process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID
  );
}

export function getClientApp(): FirebaseApp {
  getClientAuth();
  const firebaseApp = app ?? getApps()[0];
  if (!firebaseApp) {
    throw new Error("Firebase app is not initialized");
  }
  return firebaseApp;
}

export function getClientAuth(): Auth {
  if (typeof window === "undefined") {
    throw new Error("Firebase Auth is only available in the browser");
  }
  const existing = getGlobalAuth();
  if (existing) {
    auth = existing;
    return existing;
  }
  if (!auth) {
    const config = {
      apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
      authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
      projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
      storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
      messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
      appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
    };
    if (!config.apiKey || !config.authDomain || !config.projectId) {
      throw new Error(
        "Firebase client is not configured. Set NEXT_PUBLIC_FIREBASE_* in .env.local"
      );
    }
    app = getApps().length ? getApps()[0]! : initializeApp(config);
    auth = getAuth(app);
    setGlobalAuth(auth);
  }
  return auth;
}

export function getClientFirestore(): Firestore {
  if (typeof window === "undefined") {
    throw new Error("Firestore is only available in the browser");
  }
  getClientAuth();
  if (!firestore) {
    const firebaseApp = app ?? getApps()[0];
    if (!firebaseApp) {
      throw new Error("Firebase app is not initialized");
    }
    firestore = getFirestore(firebaseApp);
  }
  return firestore;
}
