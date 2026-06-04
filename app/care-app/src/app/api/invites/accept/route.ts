import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { acceptCareInvite } from "@/lib/carePair";

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: { code?: string } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }
    const code = body.code?.trim();
    if (!code) {
      return NextResponse.json({ error: "Invite code is required" }, { status: 400 });
    }

    const profile = await acceptCareInvite(ctx.uid, code, {
      email: ctx.email,
      displayName: ctx.name,
    });
    return NextResponse.json({ linked: true, ...profile });
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (e instanceof Error) {
      return NextResponse.json({ error: e.message }, { status: 400 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
