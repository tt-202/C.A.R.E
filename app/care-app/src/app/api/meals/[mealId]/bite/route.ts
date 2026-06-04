import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { getMealScope, mealOwnershipWhere } from "@/lib/carePair";
import { prisma } from "@/lib/prisma";

type RouteContext = { params: Promise<{ mealId: string }> };

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const { mealId } = await context.params;
    const ctx = await getAuthContext(request);
    const scope = await getMealScope(ctx.uid, { email: ctx.email, displayName: ctx.name });
    const body = (await request.json()) as { sectionNum?: number };
    const sectionNum = body.sectionNum;
    if (typeof sectionNum !== "number" || sectionNum < 1 || sectionNum > 4) {
      return NextResponse.json({ error: "Invalid section" }, { status: 400 });
    }
    const meal = await prisma.meal.findFirst({
      where: { id: mealId, ...mealOwnershipWhere(scope) },
    });
    if (!meal) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    if (meal.endedAt) {
      return NextResponse.json({ error: "Meal already ended" }, { status: 400 });
    }
    const data = {
      bitesTotal: { increment: 1 },
      ...(sectionNum === 1 && { section1Count: { increment: 1 } }),
      ...(sectionNum === 2 && { section2Count: { increment: 1 } }),
      ...(sectionNum === 3 && { section3Count: { increment: 1 } }),
      ...(sectionNum === 4 && { section4Count: { increment: 1 } }),
    };
    const updated = await prisma.$transaction(async (tx) => {
      await tx.mealBite.create({
        data: { mealId, sectionNum },
      });
      return tx.meal.update({
        where: { id: mealId },
        data,
      });
    });
    return NextResponse.json({
      bitesTotal: updated.bitesTotal,
      section1Count: updated.section1Count,
      section2Count: updated.section2Count,
      section3Count: updated.section3Count,
      section4Count: updated.section4Count,
    });
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
