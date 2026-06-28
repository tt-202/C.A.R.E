import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { refreshRobotLiveStatus } from "@/lib/robotLiveAdmin";
import { getRobotId } from "@/lib/robot";

export async function POST(request: NextRequest) {
  try {
    await getAuthContext(request);
    let body: { robotId?: string; clearHistory?: boolean } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty body is fine */
    }
    const robotId = body.robotId?.trim() || getRobotId();
    const snapshot = await refreshRobotLiveStatus({
      robotId,
      clearHistory: body.clearHistory !== false,
    });
    return NextResponse.json(snapshot);
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
