"use client";

import { useEffect, useRef } from "react";
import { isFcmConfigured } from "@/lib/firebasePublicConfig";
import { registerFcmTokenOnServer } from "@/lib/fcmRegisterApi";
import { obtainFcmDeviceToken, subscribeToForegroundFcm } from "@/lib/firebaseMessagingClient";
import { showBrowserNotification } from "@/hooks/useMealReminders";

type Options = {
  enabled: boolean;
  profileUid?: string;
  role: string;
  getIdToken: () => Promise<string>;
  onForegroundMessage?: (body: string) => void;
};

export function useFcmPush({
  enabled,
  profileUid,
  role,
  getIdToken,
  onForegroundMessage,
}: Options) {
  const registeredRef = useRef(false);

  useEffect(() => {
    if (!enabled || !profileUid || !isFcmConfigured()) return;

    let unsubForeground: (() => void) | null = null;
    let cancelled = false;

    (async () => {
      const token = await obtainFcmDeviceToken();
      if (cancelled || !token) return;
      if (!registeredRef.current) {
        const ok = await registerFcmTokenOnServer(getIdToken, token, role);
        if (ok) registeredRef.current = true;
      }

      unsubForeground = await subscribeToForegroundFcm((title, body) => {
        onForegroundMessage?.(body || title);
        showBrowserNotification(title, body, `fcm-${Date.now()}`);
      });
    })();

    return () => {
      cancelled = true;
      unsubForeground?.();
    };
  }, [enabled, profileUid, role, getIdToken, onForegroundMessage]);
}
