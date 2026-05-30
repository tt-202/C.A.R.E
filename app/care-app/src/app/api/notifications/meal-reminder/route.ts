import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { sendPushToUser } from "@/lib/fcmSend";
import { buildMealReminderPush, mealReminderFireKey } from "@/lib/mealReminderPush";
import { markReminderSent, wasReminderSent } from "@/lib/reminderSentFirestore";

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: {
      slotKey?: string;
      slotLabel?: string;
      time?: string;
      careRecipientName?: string;
    } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }

    const slotKey = body.slotKey?.trim();
    const slotLabel = body.slotLabel?.trim();
    const time = body.time?.trim();
    if (!slotKey || !slotLabel || !time) {
      return NextResponse.json({ error: "slotKey, slotLabel, and time are required" }, { status: 400 });
    }

    const fireKey = mealReminderFireKey(slotKey);
    if (await wasReminderSent(ctx.uid, fireKey)) {
      return NextResponse.json({ ok: true, skipped: true });
    }

    const push = buildMealReminderPush(slotLabel, time, body.careRecipientName?.trim() ?? "");
    const { sent } = await sendPushToUser(ctx.uid, {
      title: push.title,
      body: push.body,
      tag: push.tag,
    });

    if (sent > 0) await markReminderSent(ctx.uid, fireKey);

    return NextResponse.json({ ok: true, sent });
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
