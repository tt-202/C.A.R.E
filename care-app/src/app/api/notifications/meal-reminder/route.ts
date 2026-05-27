import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { sendPushToUser } from "@/lib/fcmSend";
import {
  buildMealReminderPush,
  mealReminderFireKey,
} from "@/lib/mealReminderPush";
import {
  markReminderSent,
  wasReminderSent,
} from "@/lib/reminderSentFirestore";

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
      body = {};
    }

    const slotKey = body.slotKey?.trim();
    const slotLabel = body.slotLabel?.trim();
    const time = body.time?.trim();
    const careRecipientName = body.careRecipientName?.trim() ?? "";

    if (!slotKey || !slotLabel || !time) {
      return NextResponse.json(
        {
          ok: false,
          error: "slotKey, slotLabel, and time are required",
        },
        { status: 400 },
      );
    }

    const fireKey = mealReminderFireKey(slotKey);

    const alreadySent = await wasReminderSent(ctx.uid, fireKey);
    if (alreadySent) {
      return NextResponse.json({
        ok: true,
        skipped: true,
        reason: "Reminder already sent",
      });
    }

    const push = buildMealReminderPush(
      slotLabel,
      time,
      careRecipientName,
    );

    const { sent } = await sendPushToUser(ctx.uid, {
      title: push.title,
      body: push.body,
      tag: push.tag,
      link: "/",
    });

    if (sent > 0) {
      await markReminderSent(ctx.uid, fireKey);
    }

    return NextResponse.json({
      ok: true,
      sent,
    });
  } catch (error) {
    if (error instanceof Error && error.message === "Unauthorized") {
      return NextResponse.json(
        {
          ok: false,
          error: "Unauthorized",
        },
        { status: 401 },
      );
    }

    console.error("[meal-reminder] failed", error);

    return NextResponse.json(
      {
        ok: false,
        error: "Server error",
      },
      { status: 500 },
    );
  }
}