import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { isRobotCommandType, type RobotCommandPayload } from "@/lib/robot";
import { enqueueRobotCommand, getRobotCommand } from "@/lib/robotFirestore";

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: { cmd?: string; payload?: RobotCommandPayload } = {};
    try {
      body = (await request.json()) as { cmd?: string; payload?: RobotCommandPayload };
    } catch {
      /* empty */
    }
    const cmd = body.cmd?.trim();
    if (!cmd || !isRobotCommandType(cmd)) {
      return NextResponse.json({ error: "Invalid cmd" }, { status: 400 });
    }
    const { commandId, robotId } = await enqueueRobotCommand(ctx.uid, cmd, body.payload);
    return NextResponse.json({ commandId, robotId, status: "pending" });
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

export async function GET(request: NextRequest) {
  try {
    await getAuthContext(request);
    const commandId = request.nextUrl.searchParams.get("commandId");
    const robotId = request.nextUrl.searchParams.get("robotId");
    if (!commandId || !robotId) {
      return NextResponse.json({ error: "commandId and robotId required" }, { status: 400 });
    }
    const doc = await getRobotCommand(robotId, commandId);
    if (!doc) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    return NextResponse.json({
      commandId: doc.commandId,
      robotId,
      cmd: doc.cmd,
      status: doc.status,
      error: doc.error,
    });
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
