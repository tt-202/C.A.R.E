import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { getLatestMealFinishedAlert } from "@/lib/careAlertsFirestore";

export async function GET(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    const sinceRaw = request.nextUrl.searchParams.get("since");
    const since = sinceRaw ? Number(sinceRaw) : 0;
    const latest = await getLatestMealFinishedAlert(ctx.uid);
    if (!latest || latest.finishedAtMs <= since) {
      return NextResponse.json({ alert: null });
    }
    return NextResponse.json({ alert: latest });
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
