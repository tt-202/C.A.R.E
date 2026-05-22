"use client";

import { getApps, initializeApp } from "firebase/app";
import { getMessaging, getToken, isSupported, onMessage, type Messaging } from "firebase/messaging";
import { getFirebasePublicConfig, isFcmConfigured } from "@/lib/firebasePublicConfig";

let messaging: Messaging | null = null;

async function getMessagingInstance(): Promise<Messaging | null> {
  if (typeof window === "undefined") return null;
  if (!(await isSupported())) return null;
  if (!isFcmConfigured()) return null;

  const config = getFirebasePublicConfig();
  const app = getApps().length ? getApps()[0]! : initializeApp(config);
  if (!messaging) messaging = getMessaging(app);
  return messaging;
}

export async function registerFcmServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/firebase-messaging-sw.js", { scope: "/" });
  } catch (e) {
    console.warn("[fcm] service worker registration failed", e);
    return null;
  }
}

export async function obtainFcmDeviceToken(): Promise<string | null> {
  const vapidKey = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY?.trim();
  if (!vapidKey) return null;

  const messagingInstance = await getMessagingInstance();
  if (!messagingInstance) return null;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return null;

  const sw = await registerFcmServiceWorker();
  if (!sw) return null;

  try {
    return await getToken(messagingInstance, { vapidKey, serviceWorkerRegistration: sw });
  } catch (e) {
    console.warn("[fcm] getToken failed", e);
    return null;
  }
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
