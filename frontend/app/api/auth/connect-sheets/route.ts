import { NextRequest, NextResponse } from "next/server";

const apiUrl =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  process.env.BACKEND_URL ??
  "https://crawler-automation-1.onrender.com";

export async function GET(request: NextRequest) {
  const userId = request.nextUrl.searchParams.get("user_id");
  if (!userId) {
    return NextResponse.json(
      { error: "Missing user_id query parameter" },
      { status: 400 },
    );
  }

  const returnTo = request.nextUrl.searchParams.get("return_to") || "/onboarding?step=3";
  const query = new URLSearchParams({
    user_id: userId,
    return_to: returnTo,
  });
  return NextResponse.json({ auth_url: `${apiUrl}/auth/google?${query.toString()}` });
}
