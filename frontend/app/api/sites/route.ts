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
  return notImplementedResponse("/api/sites", "GET");
}

export async function POST() {
  return notImplementedResponse("/api/sites", "POST");
}
