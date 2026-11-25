import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, STATE_COOKIE, cookieOptions, safeNext, sealSession } from "@/lib/session";

// Step 2 of "Sign in with GitHub": GitHub sends the visitor back with a one-time code, which we
// exchange for their user token, then store it (sealed) in the session cookie.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const fail = (reason: string) => {
    const response = NextResponse.redirect(new URL(`/login?error=${reason}`, request.url));
    response.cookies.set(STATE_COOKIE, "", cookieOptions(0, "/auth"));
    return response;
  };

  let saved: { state?: string; next?: string } = {};
  try {
    saved = JSON.parse(request.cookies.get(STATE_COOKIE)?.value ?? "{}");
  } catch {}
  const code = params.get("code");
  if (params.get("error")) return fail("denied");
  if (!code || !saved.state || saved.state !== params.get("state")) return fail("state");

  const exchange = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: process.env.GITHUB_CLIENT_ID,
      client_secret: process.env.GITHUB_CLIENT_SECRET,
      code,
      redirect_uri: `${request.nextUrl.origin}/auth/callback`,
    }),
  });
  const grant = (await exchange.json().catch(() => ({}))) as { access_token?: string; expires_in?: number };
  if (!grant.access_token) return fail("github");

  const profile = await fetch("https://api.github.com/user", {
    headers: { Authorization: `Bearer ${grant.access_token}`, Accept: "application/vnd.github+json" },
  });
  if (!profile.ok) return fail("github");
  const user = (await profile.json()) as { login: string; avatar_url: string };

  // GitHub user tokens last 8 hours; end the session a few minutes before the token does.
  const lifetime = (Number(grant.expires_in) || 8 * 3600) - 300;
  const session = await sealSession({
    token: grant.access_token,
    login: user.login,
    avatar: user.avatar_url,
    exp: Math.floor(Date.now() / 1000) + lifetime,
  });

  const response = NextResponse.redirect(new URL(safeNext(saved.next), request.url));
  response.cookies.set(SESSION_COOKIE, session, cookieOptions(lifetime));
  response.cookies.set(STATE_COOKIE, "", cookieOptions(0, "/auth"));
  return response;
}
