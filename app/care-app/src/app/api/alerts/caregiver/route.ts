import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { getCareContext } from "@/lib/carePair";
import { getLatestCareAlert } from "@/lib/careAlertsFirestore";

export async function GET(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    const careCtx = await getCareContext(ctx.uid, { email: ctx.email, displayName: ctx.name });
    if (!careCtx.carePairId || careCtx.role !== "caregiver") {
      return NextResponse.json({ alert: null });
    }

    const sinceRaw = request.nextUrl.searchParams.get("since");
    const since = sinceRaw ? Number(sinceRaw) : 0;
    const latest = await getLatestCareAlert(careCtx.carePairId);
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
