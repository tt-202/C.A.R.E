import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { sendPushToUsers } from "@/lib/fcmSend";
import { buildMealReminderPush, dueMealReminderSlots } from "@/lib/mealReminderPush";
import { resolveMealTimezone } from "@/lib/mealReminderTimezone";
import { markReminderSent, wasReminderSent } from "@/lib/reminderSentFirestore";
import { listFcmTokens } from "@/lib/fcmTokensFirestore";
import { listCaregiverFirebaseUidsForPair } from "@/lib/carePair";

export async function GET(request: NextRequest) {
  const secret = process.env.CRON_SECRET?.trim();
  const auth = request.headers.get("authorization");
  if (!secret || auth !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const pairs = await prisma.carePair.findMany({
      select: {
        id: true,
        careRecipientName: true,
        breakfastTime: true,
        lunchTime: true,
        dinnerTime: true,
        timezone: true,
      },
    });

    const now = new Date();
    let pushed = 0;
    let skipped = 0;
    let pairsWithCaregivers = 0;
    let pairsWithFcmTokens = 0;
    let dueSlotsNow = 0;

    for (const pair of pairs) {
      const caregiverUids = await listCaregiverFirebaseUidsForPair(pair.id);
      if (caregiverUids.length === 0) continue;
      pairsWithCaregivers += 1;

      const hasTokens = (
        await Promise.all(caregiverUids.map((uid) => listFcmTokens(uid)))
      ).some((tokens) => tokens.length > 0);
      if (!hasTokens) continue;
      pairsWithFcmTokens += 1;

      const tz = resolveMealTimezone(pair.timezone);
      const due = dueMealReminderSlots(
        {
          breakfastTime: pair.breakfastTime,
          lunchTime: pair.lunchTime,
          dinnerTime: pair.dinnerTime,
        },
        now,
        tz,
      );
      dueSlotsNow += due.length;

      for (const slot of due) {
        const alreadySent = (
          await Promise.all(caregiverUids.map((uid) => wasReminderSent(uid, slot.fireKey)))
        ).some(Boolean);
        if (alreadySent) {
          skipped += 1;
          continue;
        }

        const msg = buildMealReminderPush(
          slot.slotLabel,
          slot.time,
          pair.careRecipientName,
          slot.fireKey,
        );
        const { sent } = await sendPushToUsers(caregiverUids, {
          title: msg.title,
          body: msg.body,
          tag: msg.tag,
          alertType: "meal_reminder",
        });

        if (sent > 0) {
          await Promise.all(
            caregiverUids.map((uid) => markReminderSent(uid, slot.fireKey)),
          );
          pushed += 1;
        }
      }
    }

    return NextResponse.json({
      ok: true,
      pushed,
      skipped,
      pairs: pairs.length,
      diagnostics: {
        pairsWithCaregivers,
        pairsWithFcmTokens,
        dueSlotsNow,
        serverUtc: now.toISOString(),
      },
    });
  } catch (e) {
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
