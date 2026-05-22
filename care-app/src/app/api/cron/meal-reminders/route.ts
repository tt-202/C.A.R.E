import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { sendPushToUser } from "@/lib/fcmSend";
import { buildMealReminderPush, dueMealReminderSlots } from "@/lib/mealReminderPush";
import { markReminderSent, wasReminderSent } from "@/lib/reminderSentFirestore";
import { listFcmTokens } from "@/lib/fcmTokensFirestore";

export async function GET(request: NextRequest) {
  const secret = process.env.CRON_SECRET?.trim();
  const auth = request.headers.get("authorization");
  if (!secret || auth !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const users = await prisma.user.findMany({
      select: {
        firebaseUid: true,
        careRecipientName: true,
        breakfastTime: true,
        lunchTime: true,
        dinnerTime: true,
      },
    });

    let pushed = 0;
    let skipped = 0;

    for (const user of users) {
      const tokens = await listFcmTokens(user.firebaseUid);
      if (tokens.length === 0) continue;

      const due = dueMealReminderSlots({
        breakfastTime: user.breakfastTime,
        lunchTime: user.lunchTime,
        dinnerTime: user.dinnerTime,
      });

      for (const slot of due) {
        if (await wasReminderSent(user.firebaseUid, slot.fireKey)) {
          skipped += 1;
          continue;
        }

        const msg = buildMealReminderPush(
          slot.slotLabel,
          slot.time,
          user.careRecipientName,
        );
        const { sent } = await sendPushToUser(user.firebaseUid, {
          title: msg.title,
          body: msg.body,
          tag: msg.tag,
        });

        if (sent > 0) {
          await markReminderSent(user.firebaseUid, slot.fireKey);
          pushed += 1;
        }
      }
    }

    return NextResponse.json({ ok: true, pushed, skipped, users: users.length });
  } catch (e) {
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
