import { cert, getApps, initializeApp, type App } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { getFirestore, type Firestore } from "firebase-admin/firestore";

let adminApp: App | null = null;
let firestore: Firestore | null = null;

/** Parse service account JSON from env (handles .env \\n in private_key). */
export function parseServiceAccountJson(raw: string): Record<string, unknown> {
  let trimmed = raw.trim();
  if (
    (trimmed.startsWith("'") && trimmed.endsWith("'")) ||
    (trimmed.startsWith('"') && trimmed.endsWith('"'))
  ) {
    trimmed = trimmed.slice(1, -1);
  }
  const serviceAccount = JSON.parse(trimmed) as Record<string, unknown>;
  if (typeof serviceAccount.private_key === "string") {
    serviceAccount.private_key = serviceAccount.private_key.replace(/\\n/g, "\n");
  }
  if (typeof serviceAccount.private_key !== "string" || !serviceAccount.private_key.includes("BEGIN")) {
    throw new Error(
      'FIREBASE_SERVICE_ACCOUNT_JSON is invalid: missing a valid "private_key". Paste the full JSON from Firebase Console → Service accounts → Generate new private key.',
    );
  }
  return serviceAccount;
}

function getAdminApp(): App {
  if (adminApp) return adminApp;
  const existing = getApps()[0];
  if (existing) {
    adminApp = existing;
    return adminApp;
  }
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
  if (!raw) {
    throw new Error("FIREBASE_SERVICE_ACCOUNT_JSON is not set");
  }
  const serviceAccount = parseServiceAccountJson(raw);
  adminApp = initializeApp({ credential: cert(serviceAccount) });
  return adminApp;
}

export function getFirebaseAdminAuth() {
  return getAuth(getAdminApp());
}

export function getFirebaseAdminFirestore(): Firestore {
  if (!firestore) {
    firestore = getFirestore(getAdminApp());
  }
  return firestore;
}
