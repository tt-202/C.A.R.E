import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { resetRobotMealSession } from "@/lib/robotLiveAdmin";

export async function POST(request: NextRequest) {
  try {
    await getAuthContext(request);
    let body: { emergency?: boolean } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }
    await resetRobotMealSession({ emergency: Boolean(body.emergency) });
    return NextResponse.json({ ok: true });
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
