import { logout } from "@/app/login/actions";
import { NavLink } from "@/components/nav-link";
import { GitHubButton } from "@/components/ui";
import { getSession } from "@/lib/session";

function Shell({ children }: { children?: React.ReactNode }) {
  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
        <span className="font-semibold tracking-tight">Precedent</span>
        <nav className="flex gap-1">
          <NavLink href="/">Overview</NavLink>
          <NavLink href="/decisions">Decisions</NavLink>
          <NavLink href="/activity">Activity</NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-3">{children}</div>
      </div>
    </header>
  );
}

/** Shown while the session is read. */
export const HeaderFallback = () => <Shell />;

export async function Header() {
  const session = await getSession();
  return (
    <Shell>
      {session ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element -- a small avatar from GitHub's CDN */}
          <img src={session.avatar} alt="" width={24} height={24} className="rounded-full" />
          <span className="text-sm font-medium">{session.login}</span>
          <form action={logout}>
            <button type="submit" className="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
              Sign out
            </button>
          </form>
        </>
      ) : (
        <GitHubButton href="/auth/signin" size="sm">
          Sign in with GitHub
        </GitHubButton>
      )}
    </Shell>
  );
}
