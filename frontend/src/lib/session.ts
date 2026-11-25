// The signed-in person's session: their GitHub user token and profile, sealed (AES-GCM) in an
// httpOnly cookie with SESSION_SECRET, so the browser can neither read nor forge it.
import { cookies } from "next/headers";

export const SESSION_COOKIE = "precedent_session";
export const STATE_COOKIE = "precedent_oauth_state";

export type Session = { token: string; login: string; avatar: string; exp: number };

async function key(): Promise<CryptoKey> {
  const secret = process.env.SESSION_SECRET;
  if (!secret || secret.length < 32) throw new Error("SESSION_SECRET must be set to at least 32 characters.");
  const raw = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(secret));
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}

const toBase64 = (bytes: Uint8Array) => Buffer.from(bytes).toString("base64url");
const fromBase64 = (text: string) => new Uint8Array(Buffer.from(text, "base64url"));

export async function sealSession(session: Session): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plain = new TextEncoder().encode(JSON.stringify(session));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await key(), plain));
  return `${toBase64(iv)}.${toBase64(sealed)}`;
}

async function unsealSession(value: string | undefined): Promise<Session | null> {
  if (!value) return null;
  try {
    const [iv, sealed] = value.split(".");
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: fromBase64(iv) }, await key(), fromBase64(sealed));
    const session = JSON.parse(new TextDecoder().decode(plain)) as Session;
    return session.exp > Date.now() / 1000 ? session : null;
  } catch {
    return null; // tampered, sealed with another secret, or malformed
  }
}

/** The current visitor's session, or null for someone not signed in. */
export async function getSession(): Promise<Session | null> {
  return unsealSession((await cookies()).get(SESSION_COOKIE)?.value);
}

/** Only allow redirects back to a page on this site, never to another domain. */
export function safeNext(next: unknown): string {
  return typeof next === "string" && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export const cookieOptions = (maxAge: number, path = "/") => ({
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path,
  maxAge,
});
