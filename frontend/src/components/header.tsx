"use client";

import { usePathname } from "next/navigation";

import { logout } from "@/app/login/actions";
import { NavLink } from "@/components/nav-link";

export function Header() {
  const onLogin = usePathname() === "/login";
  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-3">
        <span className="font-semibold tracking-tight">Precedent</span>
        {!onLogin && (
          <>
            <nav className="flex gap-1">
              <NavLink href="/">Overview</NavLink>
              <NavLink href="/decisions">Decisions</NavLink>
              <NavLink href="/activity">Activity</NavLink>
            </nav>
            <form action={logout} className="ml-auto">
              <button type="submit" className="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
                Sign out
              </button>
            </form>
          </>
        )}
      </div>
    </header>
  );
}
