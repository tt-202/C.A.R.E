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

function storedTokenKey(uid: string) {
  return `care_fcm_server_token_${uid}`;
}

export function useFcmPush({
  enabled,
  profileUid,
  role,
  getIdToken,
  onForegroundMessage,
}: Options) {
  const getIdTokenRef = useRef(getIdToken);
  const onForegroundRef = useRef(onForegroundMessage);

  useEffect(() => {
    getIdTokenRef.current = getIdToken;
    onForegroundRef.current = onForegroundMessage;
  }, [getIdToken, onForegroundMessage]);

  useEffect(() => {
    if (!enabled || !profileUid || !isFcmConfigured()) return;

    let unsubForeground: (() => void) | null = null;
    let cancelled = false;

    (async () => {
      const { token } = await obtainFcmDeviceToken();
      if (cancelled || !token) return;

      const storageKey = storedTokenKey(profileUid);
      const prev =
        typeof sessionStorage !== "undefined" ? sessionStorage.getItem(storageKey) : null;
      if (prev !== token) {
        const ok = await registerFcmTokenOnServer(getIdTokenRef.current, token, role);
        if (ok && typeof sessionStorage !== "undefined") {
          sessionStorage.setItem(storageKey, token);
        }
      }

      unsubForeground = await subscribeToForegroundFcm((title, body) => {
        onForegroundRef.current?.(body || title);
        showBrowserNotification(title, body, `fcm-${Date.now()}`);
      });
    })();

    return () => {
      cancelled = true;
      unsubForeground?.();
    };
  }, [enabled, profileUid, role]);
}
