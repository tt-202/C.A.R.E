import { NextRequest, NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { getAuthContext } from "@/lib/authRequest";
import {
  createCarePairForCaregiver,
  getCareContext,
  loadCarePairProfile,
  updateCarePairProfile,
} from "@/lib/carePair";
import { ensureUser } from "@/lib/ensureUser";
import { normalizeMealSchedule } from "@/lib/mealSchedule";

function profileRouteError(e: unknown) {
  if (e instanceof Error && e.message === "Unauthorized") {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (e instanceof Error && e.message.includes("FIREBASE_SERVICE_ACCOUNT_JSON")) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
  if (e instanceof Error && (e.message.includes("Already linked") || e.message.includes("Not linked"))) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
  if (e instanceof Prisma.PrismaClientKnownRequestError) {
    console.error(e);
    return NextResponse.json(
      {
        error:
          "Database error. Confirm care pair tables exist (run prisma migrate deploy).",
      },
      { status: 500 },
    );
  }
  console.error(e);
  return NextResponse.json({ error: "Server error" }, { status: 500 });
}

export async function GET(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    await ensureUser(ctx.uid, { email: ctx.email, displayName: ctx.name });
    const profile = await loadCarePairProfile(ctx.uid);
    if (!profile) {
      return NextResponse.json({ linked: false });
    }
    return NextResponse.json({ linked: true, ...profile });
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
    const schedule = normalizeMealSchedule(body);

    const existing = await getCareContext(ctx.uid, { email: ctx.email, displayName: ctx.name });
    const profile = existing.member
      ? await updateCarePairProfile(ctx.uid, {
          careRecipientName,
          caregiverName,
          ...schedule,
        })
      : await createCarePairForCaregiver(ctx.uid, {
          email: ctx.email,
          displayName: ctx.name ?? caregiverName,
          careRecipientName,
          caregiverName,
          ...schedule,
        });

    return NextResponse.json({ linked: true, ...profile });
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

    const careCtx = await getCareContext(ctx.uid, { email: ctx.email, displayName: ctx.name });
    if (!careCtx.member) {
      return NextResponse.json({ error: "Not linked to a care pair" }, { status: 400 });
    }

    const schedule = normalizeMealSchedule(body);
    const profile = await updateCarePairProfile(ctx.uid, {
      ...(body.careRecipientName?.trim() ? { careRecipientName: body.careRecipientName.trim() } : {}),
      ...(body.caregiverName?.trim() ? { caregiverName: body.caregiverName.trim() } : {}),
      ...schedule,
    });

    return NextResponse.json({ linked: true, ...profile });
  } catch (e) {
    return profileRouteError(e);
  }
}
