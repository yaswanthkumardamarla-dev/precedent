import { type NextRequest, NextResponse } from "next/server";

import { STATE_COOKIE, cookieOptions, safeNext } from "@/lib/session";

// Step 1 of "Sign in with GitHub": send the visitor to GitHub, remembering a random state to check on return.
export async function GET(request: NextRequest) {
  const clientId = process.env.GITHUB_CLIENT_ID;
  if (!clientId) return new NextResponse("GITHUB_CLIENT_ID is not set.", { status: 503 });

  const state = crypto.randomUUID();
  const next = safeNext(request.nextUrl.searchParams.get("next"));
  const authorize = new URL("https://github.com/login/oauth/authorize");
  authorize.searchParams.set("client_id", clientId);
  authorize.searchParams.set("redirect_uri", `${request.nextUrl.origin}/auth/callback`);
  authorize.searchParams.set("state", state);

  const response = NextResponse.redirect(authorize);
  response.cookies.set(STATE_COOKIE, JSON.stringify({ state, next }), cookieOptions(600, "/auth"));
  return response;
}
