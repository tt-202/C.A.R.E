import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { publishMealFinishedAlert } from "@/lib/careAlertsFirestore";
import { formatMealDoneNotification } from "@/lib/mealDoneAlert";
import { sendPushToUser } from "@/lib/fcmSend";

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: {
      careRecipientName?: string;
      caregiverName?: string;
      bitesTotal?: number;
      plannedMealTime?: string;
    } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }

    const bitesTotal = typeof body.bitesTotal === "number" ? body.bitesTotal : 0;

    const alert = await publishMealFinishedAlert(ctx.uid, {
      careRecipientName: body.careRecipientName?.trim() || "User",
      caregiverName: body.caregiverName?.trim() || "Caregiver",
      bitesTotal,
      plannedMealTime: body.plannedMealTime?.trim() || "",
    });

    const { title, body: pushBody } = formatMealDoneNotification(alert);
    const push = await sendPushToUser(ctx.uid, {
      title,
      body: pushBody,
      tag: `meal-done-${alert.finishedAtMs}`,
    });

    return NextResponse.json({ ok: true, alert, push });
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (e instanceof Error && e.message.includes("FIREBASE_SERVICE_ACCOUNT_JSON")) {
      return NextResponse.json({ error: e.message }, { status: 500 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
