import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { createCareInvite, previewCareInvite } from "@/lib/carePair";

function inviteError(e: unknown) {
  if (e instanceof Error && e.message === "Unauthorized") {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (e instanceof Error) {
    const status =
      e.message.includes("Only caregivers") ||
      e.message.includes("already linked") ||
      e.message.includes("already has")
        ? 400
        : 500;
    return NextResponse.json({ error: e.message }, { status });
  }
  console.error(e);
  return NextResponse.json({ error: "Server error" }, { status: 500 });
}

export async function GET(request: NextRequest) {
  try {
    const code = request.nextUrl.searchParams.get("code")?.trim();
    if (!code) {
      return NextResponse.json({ error: "code is required" }, { status: 400 });
    }
    const preview = await previewCareInvite(code);
    if (!preview) {
      return NextResponse.json({ error: "Invite not found or expired" }, { status: 404 });
    }
    return NextResponse.json(preview);
  } catch (e) {
    return inviteError(e);
  }
}

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: { role?: "user" | "caregiver" } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }
    const role = body.role === "caregiver" ? "caregiver" : "user";
    const invite = await createCareInvite(ctx.uid, role);
    return NextResponse.json(invite);
  } catch (e) {
    return inviteError(e);
  }
}
