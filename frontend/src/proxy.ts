import { type NextRequest, NextResponse } from "next/server";

// Password-protects every page and Server Action with HTTP Basic auth (any username, DASHBOARD_PASSWORD).
// In production a missing password locks the dashboard instead of leaving it open.

function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function passwordFrom(request: NextRequest): string | null {
  const header = request.headers.get("authorization");
  if (!header?.startsWith("Basic ")) return null;
  try {
    const decoded = atob(header.slice(6));
    return decoded.slice(decoded.indexOf(":") + 1);
  } catch {
    return null;
  }
}

export function proxy(request: NextRequest) {
  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) {
    if (process.env.NODE_ENV === "production") {
      return new NextResponse("DASHBOARD_PASSWORD is not set, so the dashboard is locked.", { status: 503 });
    }
    return NextResponse.next(); // local development without a password
  }

  const given = passwordFrom(request);
  if (given !== null && safeEqual(given, expected)) return NextResponse.next();

  return new NextResponse("Sign in to Precedent.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Precedent", charset="UTF-8"' },
  });
}

export const config = {
  // Everything except Next's own static files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
