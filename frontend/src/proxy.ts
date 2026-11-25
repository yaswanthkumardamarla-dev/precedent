import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, safeEqual, sessionValue } from "@/lib/session";

// Every page and Server Action needs a session cookie, which /login hands out for DASHBOARD_PASSWORD.
// In production a missing password locks the dashboard instead of leaving it open.

export async function proxy(request: NextRequest) {
  const password = process.env.DASHBOARD_PASSWORD;
  if (!password) {
    if (process.env.NODE_ENV === "production") {
      return new NextResponse("DASHBOARD_PASSWORD is not set, so the dashboard is locked.", { status: 503 });
    }
    return NextResponse.next(); // local development without a password
  }

  const { pathname, search } = request.nextUrl;
  if (pathname === "/login") return NextResponse.next();

  const cookie = request.cookies.get(SESSION_COOKIE)?.value;
  if (cookie && safeEqual(cookie, await sessionValue(password))) return NextResponse.next();

  if (request.method !== "GET") return new NextResponse("Sign in first.", { status: 401 });
  const login = new URL("/login", request.url);
  if (pathname !== "/") login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except Next's own static files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
