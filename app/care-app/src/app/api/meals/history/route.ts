import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { getMealScope, mealOwnershipWhere } from "@/lib/carePair";
import { mealToHistoryEntry } from "@/lib/mealDto";
import { prisma } from "@/lib/prisma";

export async function GET(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    const scope = await getMealScope(ctx.uid, { email: ctx.email, displayName: ctx.name });
    const meals = await prisma.meal.findMany({
      where: { ...mealOwnershipWhere(scope), endedAt: { not: null } },
      orderBy: { endedAt: "desc" },
    });
    return NextResponse.json({
      meals: meals.map((m) => mealToHistoryEntry(m)),
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

export async function DELETE(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    const scope = await getMealScope(ctx.uid, { email: ctx.email, displayName: ctx.name });
    await prisma.meal.deleteMany({ where: mealOwnershipWhere(scope) });
    return NextResponse.json({ ok: true });
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
