// A signed-in browser carries a cookie whose value is derived from DASHBOARD_PASSWORD.
// Changing the password therefore signs everyone out.

export const SESSION_COOKIE = "precedent_session";
export const SESSION_MAX_AGE = 60 * 60 * 24 * 30; // 30 days

export async function sessionValue(password: string): Promise<string> {
  const bytes = new TextEncoder().encode(`precedent-session:${password}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Only allow redirects back to a page on this site, never to another domain. */
export function safeNext(next: unknown): string {
  return typeof next === "string" && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}
