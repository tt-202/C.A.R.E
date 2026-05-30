import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { sendPushToUser } from "@/lib/fcmSend";
import { listFcmTokens } from "@/lib/fcmTokensFirestore";

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    const tokens = await listFcmTokens(ctx.uid);
    if (tokens.length === 0) {
      return NextResponse.json(
        {
          error:
            "No push token on this device yet. Allow notifications, reload, and wait a few seconds.",
        },
        { status: 400 },
      );
    }

    const { sent, failed, errors } = await sendPushToUser(ctx.uid, {
      title: "C.A.R.E — Test push",
      body: "Firebase Cloud Messaging is working on this device.",
      tag: "care-fcm-test",
    });

    if (sent === 0) {
      return NextResponse.json({
        ok: false,
        sent,
        failed,
        errors,
        error:
          errors[0] ??
          "Push send failed. Confirm VAPID key and service account are from the same Firebase project.",
      }, { status: 502 });
    }

    return NextResponse.json({ ok: true, sent, failed, errors });
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
