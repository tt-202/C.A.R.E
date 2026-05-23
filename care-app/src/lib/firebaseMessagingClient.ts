"use client";

import { getMessaging, getToken, isSupported, onMessage, type Messaging } from "firebase/messaging";
import { getClientApp } from "@/lib/firebaseClient";
import { isFcmConfigured } from "@/lib/firebasePublicConfig";

let messaging: Messaging | null = null;
let tokenInFlight: Promise<FcmTokenResult> | null = null;

export type FcmTokenResult = {
  token: string | null;
  error?: string;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatFcmError(e: unknown): string {
  if (e && typeof e === "object" && "code" in e) {
    const code = String((e as { code: string }).code);
    const message = "message" in e ? String((e as { message: string }).message) : "";
    if (code === "messaging/permission-blocked") {
      return "Notifications are blocked. Allow them in site settings, then reload.";
    }
    if (code === "messaging/failed-service-worker-registration") {
      return "Service worker failed to register. Reload the page and use only one localhost port (close other npm run dev tabs).";
    }
    if (code === "messaging/token-subscribe-failed") {
      return "FCM subscribe failed — check NEXT_PUBLIC_FIREBASE_VAPID_KEY matches Firebase Console → Cloud Messaging → Web Push.";
    }
    return message ? `${code}: ${message}` : code;
  }
  return e instanceof Error ? e.message : "Unknown FCM error";
}

async function waitForServiceWorkerActive(
  registration: ServiceWorkerRegistration,
  timeoutMs = 12_000,
): Promise<void> {
  if (registration.active) return;

  const worker = registration.installing ?? registration.waiting;
  if (!worker) {
    await navigator.serviceWorker.ready;
    if (registration.active) return;
    throw new Error("Service worker is not active");
  }

  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error("Service worker activation timed out"));
    }, timeoutMs);

    const onStateChange = () => {
      if (worker.state === "activated") {
        clearTimeout(timer);
        worker.removeEventListener("statechange", onStateChange);
        resolve();
      }
      if (worker.state === "redundant") {
        clearTimeout(timer);
        worker.removeEventListener("statechange", onStateChange);
        reject(new Error("Service worker became redundant"));
      }
    };
    worker.addEventListener("statechange", onStateChange);
    onStateChange();
  });
}

async function getMessagingInstance(): Promise<Messaging | null> {
  if (typeof window === "undefined") return null;
  if (!(await isSupported())) return null;
  if (!isFcmConfigured()) return null;

  if (!messaging) {
    messaging = getMessaging(getClientApp());
  }
  return messaging;
}

export async function registerFcmServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/firebase-messaging-sw.js", {
      scope: "/",
      updateViaCache: "none",
    });
  } catch (e) {
    console.warn("[fcm] service worker registration failed", e);
    return null;
  }
}

async function obtainFcmDeviceTokenImpl(): Promise<FcmTokenResult> {
  const vapidKey = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY?.trim();
  if (!vapidKey) {
    return { token: null, error: "NEXT_PUBLIC_FIREBASE_VAPID_KEY is missing" };
  }

  if (!(await isSupported())) {
    return { token: null, error: "FCM is not supported in this browser (use Chrome or Edge on desktop)" };
  }

  if (typeof Notification === "undefined") {
    return { token: null, error: "Notifications are not supported" };
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    return { token: null, error: "Notification permission was not granted" };
  }

  const sw = await registerFcmServiceWorker();
  if (!sw) {
    return { token: null, error: "Could not register firebase-messaging-sw.js" };
  }

  try {
    await waitForServiceWorkerActive(sw);
    await navigator.serviceWorker.ready;
  } catch (e) {
    return {
      token: null,
      error: `${formatFcmError(e)} Try a hard reload (Cmd+Shift+R).`,
    };
  }

  const messagingInstance = await getMessagingInstance();
  if (!messagingInstance) {
    return { token: null, error: "Could not initialize Firebase Messaging" };
  }

  let lastError = "Could not get FCM token";
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const token = await getToken(messagingInstance, {
        vapidKey,
        serviceWorkerRegistration: sw,
      });
      if (token) {
        if (process.env.NODE_ENV === "development") {
          const prev = sessionStorage.getItem("care_fcm_token_logged");
          if (prev !== token) {
            sessionStorage.setItem("care_fcm_token_logged", token);
            console.info("[fcm] device token (for Firebase Console tests):", token);
          }
        }
        return { token };
      }
    } catch (e) {
      lastError = formatFcmError(e);
      console.warn(`[fcm] getToken failed (attempt ${attempt + 1}/3)`, e);
      if (attempt < 2) await sleep(800 * (attempt + 1));
    }
  }

  const portHint =
    typeof window !== "undefined" && window.location.port && window.location.port !== "3000"
      ? ` You are on port ${window.location.port} — close other dev servers and use one URL only.`
      : "";

  return {
    token: null,
    error: `${lastError}.${portHint} Check DevTools → Console for [fcm] and that /firebase-messaging-sw.js returns 200.`,
  };
}

/** Obtain FCM device token (serialized — safe to call from multiple hooks at once). */
export async function obtainFcmDeviceToken(): Promise<FcmTokenResult> {
  if (!tokenInFlight) {
    tokenInFlight = obtainFcmDeviceTokenImpl().finally(() => {
      tokenInFlight = null;
    });
  }
  return tokenInFlight;
}

export async function subscribeToForegroundFcm(
  onPayload: (title: string, body: string) => void,
): Promise<(() => void) | null> {
  const messagingInstance = await getMessagingInstance();
  if (!messagingInstance) return null;

  return onMessage(messagingInstance, (payload) => {
    const title = payload.notification?.title ?? "C.A.R.E";
    const body = payload.notification?.body ?? "";
    onPayload(title, body);
  });
}
