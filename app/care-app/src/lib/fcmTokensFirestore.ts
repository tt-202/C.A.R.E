import { createHash } from "crypto";
import { FieldValue } from "firebase-admin/firestore";
import { getFirebaseAdminFirestore } from "@/lib/firebaseAdmin";

export type FcmTokenDoc = {
  token: string;
  role: string;
  userAgent: string;
  updatedAt: ReturnType<typeof FieldValue.serverTimestamp>;
};

function tokenDocId(token: string): string {
  return createHash("sha256").update(token).digest("hex").slice(0, 40);
}

function tokensCollection(userId: string) {
  return getFirebaseAdminFirestore().collection("users").doc(userId).collection("fcmTokens");
}

export async function saveFcmToken(
  userId: string,
  token: string,
  opts?: { role?: string; userAgent?: string },
): Promise<void> {
  await tokensCollection(userId)
    .doc(tokenDocId(token))
    .set({
      token,
      role: opts?.role ?? "",
      userAgent: opts?.userAgent ?? "",
      updatedAt: FieldValue.serverTimestamp(),
    });
}

export async function removeFcmToken(userId: string, token: string): Promise<void> {
  await tokensCollection(userId).doc(tokenDocId(token)).delete();
}

export async function listFcmTokens(userId: string): Promise<string[]> {
  const snap = await tokensCollection(userId).get();
  const tokens: string[] = [];
  for (const doc of snap.docs) {
    const t = doc.data().token;
    if (typeof t === "string" && t.length > 0) tokens.push(t);
  }
  return tokens;
}
