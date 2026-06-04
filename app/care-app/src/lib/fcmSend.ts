import { getMessaging, type MulticastMessage } from "firebase-admin/messaging";
import { getAdminApp } from "@/lib/firebaseAdmin";
import { listFcmTokens, removeFcmToken } from "@/lib/fcmTokensFirestore";

export type PushPayload = {
  title: string;
  body: string;
  /** Opens this path when the notification is clicked (web). */
  link?: string;
  tag?: string;
};

function getAdminMessaging() {
  getAdminApp();
  return getMessaging();
}

export async function sendPushToUser(
  userId: string,
  payload: PushPayload,
): Promise<{ sent: number; failed: number; errors: string[] }> {
  const tokens = await listFcmTokens(userId);
  if (tokens.length === 0) return { sent: 0, failed: 0, errors: [] };

  const link = payload.link ?? "/";
  const message: MulticastMessage = {
    tokens,
    notification: {
      title: payload.title,
      body: payload.body,
    },
    webpush: {
      notification: {
        title: payload.title,
        body: payload.body,
        tag: payload.tag,
      },
      fcmOptions: { link },
    },
  };

  const res = await getAdminMessaging().sendEachForMulticast(message);
  let sent = 0;
  let failed = 0;
  const errors: string[] = [];

  await Promise.all(
    res.responses.map(async (r, i) => {
      if (r.success) {
        sent += 1;
        return;
      }
      failed += 1;
      const msg = r.error?.message ?? r.error?.code ?? "send failed";
      errors.push(msg);
      console.warn("[fcm] send failed", r.error);
      const code = r.error?.code;
      if (
        code === "messaging/invalid-registration-token" ||
        code === "messaging/registration-token-not-registered"
      ) {
        await removeFcmToken(userId, tokens[i]!);
      }
    }),
  );

  return { sent, failed, errors };
}

export async function sendPushToUsers(
  userIds: string[],
  payload: PushPayload,
): Promise<{ sent: number; failed: number; errors: string[] }> {
  let sent = 0;
  let failed = 0;
  const errors: string[] = [];
  const unique = [...new Set(userIds.filter(Boolean))];
  for (const userId of unique) {
    const result = await sendPushToUser(userId, payload);
    sent += result.sent;
    failed += result.failed;
    errors.push(...result.errors);
  }
  return { sent, failed, errors };
}
