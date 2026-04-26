import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const protectedRoutes = ["/dashboard", "/config", "/logs", "/users"];
const publicRoutes = ["/onboarding", "/onboarding/callback", "/login"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (publicRoutes.some((route) => pathname.startsWith(route))) {
    return NextResponse.next();
  }

  if (protectedRoutes.some((route) => pathname.startsWith(route))) {
    const token = request.cookies.get("crawler_token")?.value;
    if (!token) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      return NextResponse.redirect(url);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/config/:path*", "/logs/:path*", "/users/:path*", "/onboarding/:path*", "/login"],
};
