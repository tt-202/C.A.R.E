export async function registerFcmTokenOnServer(
  getIdToken: () => Promise<string>,
  token: string,
  role: string,
): Promise<boolean> {
  try {
    const idToken = await getIdToken();
    const res = await fetch("/api/notifications/register", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${idToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token, role }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function sendTestPushFromServer(getIdToken: () => Promise<string>): Promise<{
  ok: boolean;
  sent?: number;
  error?: string;
}> {
  try {
    const idToken = await getIdToken();
    const res = await fetch("/api/notifications/test", {
      method: "POST",
      headers: { Authorization: `Bearer ${idToken}` },
    });
    const body = (await res.json().catch(() => ({}))) as {
      ok?: boolean;
      sent?: number;
      failed?: number;
      errors?: string[];
      error?: string;
    };
    if (!res.ok) {
      const detail = body.errors?.length ? body.errors.join("; ") : body.error;
      return { ok: false, error: detail ?? `Server error (${res.status})` };
    }
    return { ok: true, sent: body.sent ?? 0 };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Network error" };
  }
}

export async function triggerMealReminderPush(
  getIdToken: () => Promise<string>,
  payload: {
    slotKey: string;
    slotLabel: string;
    time: string;
    careRecipientName: string;
  },
): Promise<void> {
  try {
    const idToken = await getIdToken();
    await fetch("/api/notifications/meal-reminder", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${idToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch {
    /* optional */
  }
}
