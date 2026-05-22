import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { ensureUser } from "@/lib/ensureUser";
import { normalizeMealSchedule } from "@/lib/mealSchedule";

function profileJson(user: {
  careRecipientName: string;
  caregiverName: string;
  breakfastTime: string;
  lunchTime: string;
  dinnerTime: string;
}) {
  const schedule = normalizeMealSchedule(user);
  return {
    careRecipientName: user.careRecipientName,
    caregiverName: user.caregiverName,
    breakfastTime: schedule.breakfastTime,
    lunchTime: schedule.lunchTime,
    dinnerTime: schedule.dinnerTime,
  };
}

export async function GET(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    const user = await ensureUser(ctx.uid, { email: ctx.email, displayName: ctx.name });
    return NextResponse.json(profileJson(user));
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

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: {
      careRecipientName?: string;
      caregiverName?: string;
      breakfastTime?: string;
      lunchTime?: string;
      dinnerTime?: string;
    } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }
    const careRecipientName = body.careRecipientName?.trim() ?? "";
    const caregiverName = body.caregiverName?.trim() ?? "";
    if (!careRecipientName || !caregiverName) {
      return NextResponse.json({ error: "Both names are required" }, { status: 400 });
    }
    const schedule = normalizeMealSchedule({
      breakfastTime: body.breakfastTime,
      lunchTime: body.lunchTime,
      dinnerTime: body.dinnerTime,
    });
    const user = await ensureUser(ctx.uid, {
      email: ctx.email,
      displayName: ctx.name ?? caregiverName,
      careRecipientName,
      caregiverName,
      breakfastTime: schedule.breakfastTime,
      lunchTime: schedule.lunchTime,
      dinnerTime: schedule.dinnerTime,
    });
    return NextResponse.json(profileJson(user));
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

export async function PATCH(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: { breakfastTime?: string; lunchTime?: string; dinnerTime?: string } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }
    const schedule = normalizeMealSchedule(body);
    const existing = await ensureUser(ctx.uid, { email: ctx.email, displayName: ctx.name });
    const user = await ensureUser(ctx.uid, {
      breakfastTime: schedule.breakfastTime,
      lunchTime: schedule.lunchTime,
      dinnerTime: schedule.dinnerTime,
      careRecipientName: existing.careRecipientName,
      caregiverName: existing.caregiverName,
    });
    return NextResponse.json(profileJson(user));
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
