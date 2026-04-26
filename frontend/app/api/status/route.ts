function notImplementedResponse(endpoint: string, method: string) {
  return Response.json(
    {
      ok: false,
      endpoint,
      method,
      message: "Not implemented yet.",
    },
    { status: 501 }
  );
}

export async function GET() {
  return notImplementedResponse("/api/status", "GET");
}

export async function POST() {
  return notImplementedResponse("/api/status", "POST");
}
