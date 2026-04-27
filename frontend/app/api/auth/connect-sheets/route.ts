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

  const response = await fetch(
    `${apiUrl}/auth/google?user_id=${encodeURIComponent(userId)}`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    return NextResponse.json({ error: "Failed to get OAuth URL" }, { status: 502 });
  }

  const data = await response.json();
  return NextResponse.json({ auth_url: data.auth_url as string });
}
