/** Web client Firebase config from NEXT_PUBLIC_* env vars. */
export function getFirebasePublicConfig() {
  return {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
    storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET ?? "",
    messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID ?? "",
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? "",
  };
}

export function isFirebasePublicConfigured(): boolean {
  const c = getFirebasePublicConfig();
  return Boolean(c.apiKey && c.authDomain && c.projectId && c.appId);
}

export function isFcmConfigured(): boolean {
  return isFirebasePublicConfigured() && Boolean(process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY?.trim());
}
