import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { getMealScope, mealOwnershipWhere } from "@/lib/carePair";
import { mealToHistoryEntry } from "@/lib/mealDto";
import { prisma } from "@/lib/prisma";

type RouteContext = { params: Promise<{ mealId: string }> };

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const { mealId } = await context.params;
    const ctx = await getAuthContext(request);
    const scope = await getMealScope(ctx.uid, { email: ctx.email, displayName: ctx.name });
    let body: { plannedMealTime?: string } = {};
    try {
      body = (await request.json()) as { plannedMealTime?: string };
    } catch {
      /* empty */
    }
    const meal = await prisma.meal.findFirst({
      where: { id: mealId, ...mealOwnershipWhere(scope) },
    });
    if (!meal) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    if (meal.endedAt) {
      return NextResponse.json({ error: "Already ended" }, { status: 400 });
    }
    const end = new Date();
    const durationMs = end.getTime() - meal.startedAt.getTime();

    if (meal.bitesTotal === 0 && durationMs < 3000) {
      await prisma.meal.delete({ where: { id: mealId } });
      return NextResponse.json({ cancelled: true });
    }

    const updated = await prisma.meal.update({
      where: { id: mealId },
      data: {
        endedAt: end,
        durationMs,
        plannedMealTime: body.plannedMealTime ?? meal.plannedMealTime,
      },
    });
    return NextResponse.json({ ok: true, meal: mealToHistoryEntry(updated) });
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
