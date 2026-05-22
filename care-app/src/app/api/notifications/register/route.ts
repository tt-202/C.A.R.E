import { NextRequest, NextResponse } from "next/server";
import { getAuthContext } from "@/lib/authRequest";
import { saveFcmToken } from "@/lib/fcmTokensFirestore";

export async function POST(request: NextRequest) {
  try {
    const ctx = await getAuthContext(request);
    let body: { token?: string; role?: string } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      /* empty */
    }
    const token = body.token?.trim();
    if (!token) {
      return NextResponse.json({ error: "token is required" }, { status: 400 });
    }

    await saveFcmToken(ctx.uid, token, {
      role: body.role?.trim() ?? "",
      userAgent: request.headers.get("user-agent") ?? "",
    });

    return NextResponse.json({ ok: true });
  } catch (e) {
    if (e instanceof Error && e.message === "Unauthorized") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error(e);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
