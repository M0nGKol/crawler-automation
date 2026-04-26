import { NextRequest } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "";

export async function GET(request: NextRequest) {
  const userId = request.nextUrl.searchParams.get("user_id");
  if (!userId) {
    return Response.json(
      { error: "Missing user_id query parameter" },
      { status: 400 },
    );
  }

  const response = await fetch(
    `${backendUrl}/auth/google?user_id=${encodeURIComponent(userId)}`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    return Response.json({ error: "Failed to get OAuth URL" }, { status: 502 });
  }

  const data = await response.json();
  return Response.json({ auth_url: data.auth_url as string });
}
