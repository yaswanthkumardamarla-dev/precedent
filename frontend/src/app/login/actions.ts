"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { SESSION_COOKIE, SESSION_MAX_AGE, safeEqual, safeNext, sessionValue } from "@/lib/session";

export async function login(formData: FormData) {
  const password = process.env.DASHBOARD_PASSWORD;
  const given = formData.get("password");
  const next = safeNext(formData.get("next"));

  if (!password || typeof given !== "string" || !safeEqual(given, password)) {
    const params = new URLSearchParams({ error: "1" });
    if (next !== "/") params.set("next", next);
    redirect(`/login?${params}`);
  }

  (await cookies()).set(SESSION_COOKIE, await sessionValue(password), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });
  redirect(next);
}

export async function logout() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}
