import { NextRequest, NextResponse } from "next/server";
import { publishAndPushCaregiverPlateAlert } from "@/lib/publishCaregiverMealAlert";

type RobotPlateAlertBody = {
  robotId?: string;
  section?: number;
  status?: string;
};

/** Jetson YOLO empty plate → caregiver push (shared secret, not user JWT). */
export async function POST(request: NextRequest) {
  try {
    const expectedSecret = process.env.ROBOT_SHARED_SECRET?.trim();

    if (!expectedSecret) {
      return NextResponse.json(
        { error: "ROBOT_SHARED_SECRET is not configured on the server." },
        { status: 500 },
      );
    }

    const providedSecret = request.headers.get("x-robot-secret")?.trim();

    if (providedSecret !== expectedSecret) {
      return NextResponse.json({ error: "Unauthorized robot request." }, { status: 401 });
    }

    const carePairId = process.env.ROBOT_CARE_PAIR_ID?.trim();

    if (!carePairId) {
      return NextResponse.json(
        { error: "ROBOT_CARE_PAIR_ID is not configured on the server." },
        { status: 500 },
      );
    }

    let body: RobotPlateAlertBody = {};

    try {
      body = (await request.json()) as RobotPlateAlertBody;
    } catch {
      body = {};
    }

    const status = (body.status ?? "empty").trim().toLowerCase();
    if (status !== "empty") {
      return NextResponse.json({ ok: true, skipped: true, reason: "only empty plate triggers alert" });
    }

    const robotId = body.robotId?.trim() || "care-01";
    const section = typeof body.section === "number" ? body.section : 1;

    const careRecipientName =
      process.env.ROBOT_CARE_RECIPIENT_NAME?.trim() || "C.A.R.E user";

    const caregiverName = process.env.ROBOT_CAREGIVER_NAME?.trim() || "Caregiver";

    const alert = await publishAndPushCaregiverPlateAlert({
      carePairId,
      careRecipientName,
      caregiverName,
      robotId,
      section,
      plateStatus: status,
    });

    return NextResponse.json({
      ok: true,
      alert,
    });
  } catch (e) {
    console.error("[robot plate-alert]", e);

    if (e instanceof Error && e.message.includes("FIREBASE_SERVICE_ACCOUNT_JSON")) {
      return NextResponse.json({ error: e.message }, { status: 500 });
    }

    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
