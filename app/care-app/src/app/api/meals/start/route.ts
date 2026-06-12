import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { getMealScope } from "@/lib/carePair";
import { startRobotMealSession } from "@/lib/robotLiveAdmin";
import { prisma } from "@/lib/prisma";

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    const scope = await getMealScope(ctx.uid, { email: ctx.email, displayName: ctx.name });
    let body: { plannedMealTime?: string } = {};
    try {
      body = (await request.json()) as { plannedMealTime?: string };
    } catch {
      /* empty */
    }
    const meal = await prisma.meal.create({
      data: {
        userId: scope.userId,
        carePairId: scope.carePairId,
        startedAt: new Date(),
        plannedMealTime: body.plannedMealTime ?? null,
      },
    });
    try {
      await startRobotMealSession();
    } catch (resetErr) {
      console.warn("[meal start] robot session start failed", resetErr);
    }
    return NextResponse.json({ mealId: meal.id });
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (e instanceof Error && e.message === "FIREBASE_SERVICE_ACCOUNT_JSON is not set") {
      return NextResponse.json({ error: "Server misconfigured" }, { status: 500 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
