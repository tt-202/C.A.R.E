"use client";

import { isSupported } from "firebase/messaging";
import { isFcmConfigured, isFirebasePublicConfigured } from "@/lib/firebasePublicConfig";
import { obtainFcmDeviceToken } from "@/lib/firebaseMessagingClient";
import { registerFcmTokenOnServer } from "@/lib/fcmRegisterApi";

export type FcmSetupResult = {
  ok: boolean;
  tokenPreview: string | null;
  error: string | null;
  steps: string[];
};

export async function setupPushOnThisDevice(
  getIdToken: () => Promise<string>,
  role: string,
): Promise<FcmSetupResult> {
  const steps: string[] = [];

  if (!isFirebasePublicConfigured()) {
    return { ok: false, tokenPreview: null, error: "Firebase web env vars are missing.", steps };
  }
  steps.push("Firebase web config OK");

  if (!isFcmConfigured()) {
    return {
      ok: false,
      tokenPreview: null,
      error: "NEXT_PUBLIC_FIREBASE_VAPID_KEY is missing. Add the Web Push public key from Firebase Console.",
      steps,
    };
  }
  steps.push("VAPID key present");

  if (typeof window === "undefined" || !("Notification" in window)) {
    return { ok: false, tokenPreview: null, error: "This browser does not support notifications.", steps };
  }

  const supported = await isSupported();
  if (!supported) {
    return {
      ok: false,
      tokenPreview: null,
      error: "FCM is not supported here (try Chrome or Edge on desktop; Safari/iOS is limited).",
      steps,
    };
  }
  steps.push("FCM supported in this browser");

  if (Notification.permission === "denied") {
    return {
      ok: false,
      tokenPreview: null,
      error: "Notifications are blocked. Allow them in browser site settings, then reload.",
      steps,
    };
  }

  const token = await obtainFcmDeviceToken();
  if (!token) {
    return {
      ok: false,
      tokenPreview: null,
      error:
        Notification.permission !== "granted"
          ? "Notification permission was not granted. Click Allow when the browser asks."
          : "Could not get FCM token. Check DevTools → Console for [fcm] errors and that /firebase-messaging-sw.js loads (status 200).",
      steps,
    };
  }
  steps.push(`FCM token obtained (${token.slice(0, 12)}…)`);

  const saved = await registerFcmTokenOnServer(getIdToken, token, role);
  if (!saved) {
    return {
      ok: false,
      tokenPreview: token.slice(0, 20) + "…",
      error: "Token obtained but server registration failed. Sign in again and check FIREBASE_SERVICE_ACCOUNT_JSON.",
      steps,
    };
  }
  steps.push("Token saved on server");

  return { ok: true, tokenPreview: token.slice(0, 20) + "…", error: null, steps };
}
