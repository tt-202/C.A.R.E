import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { getAuthContext } from "@/lib/authRequest";
import { ensureUser } from "@/lib/ensureUser";
import { normalizeMealSchedule } from "@/lib/mealSchedule";

function profileRouteError(e: unknown) {
  if (e instanceof Error && e.message === "Unauthorized") {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (e instanceof Error && e.message.includes("FIREBASE_SERVICE_ACCOUNT_JSON")) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
  if (e instanceof Prisma.PrismaClientKnownRequestError) {
    console.error(e);
    return NextResponse.json(
      {
        error:
          "Database error. Confirm breakfastTime, lunchTime, and dinnerTime columns exist on the User table in Neon.",
      },
      { status: 500 },
    );
  }
  console.error(e);
  return NextResponse.json({ error: "Server error" }, { status: 500 });
}

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
    return profileRouteError(e);
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
    return profileRouteError(e);
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: {
      breakfastTime?: string;
      lunchTime?: string;
      dinnerTime?: string;
      careRecipientName?: string;
      caregiverName?: string;
    } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }
    const schedule = normalizeMealSchedule(body);
    const existing = await ensureUser(ctx.uid, { email: ctx.email, displayName: ctx.name });
    const careRecipientName = body.careRecipientName?.trim() || existing.careRecipientName;
    const caregiverName = body.caregiverName?.trim() || existing.caregiverName;
    const user = await ensureUser(ctx.uid, {
      breakfastTime: schedule.breakfastTime,
      lunchTime: schedule.lunchTime,
      dinnerTime: schedule.dinnerTime,
      ...(body.careRecipientName?.trim()
        ? { careRecipientName }
        : {}),
      ...(body.caregiverName?.trim() ? { caregiverName } : {}),
    });
    return NextResponse.json(profileJson(user));
  } catch (e) {
    return profileRouteError(e);
  }
}
