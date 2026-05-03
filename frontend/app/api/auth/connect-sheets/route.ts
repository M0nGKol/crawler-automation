import { NextRequest, NextResponse } from "next/server";

const apiUrl =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  process.env.BACKEND_URL ??
  "https://crawler-automation-1.onrender.com";

export async function GET(request: NextRequest) {
  const returnTo = request.nextUrl.searchParams.get("return_to") || "/dashboard";
  const query = new URLSearchParams({ return_to: returnTo });
  return NextResponse.json({ auth_url: `${apiUrl}/auth/google?${query.toString()}` });
}
