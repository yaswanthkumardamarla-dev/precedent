import { Suspense } from "react";

import { GitHubButton } from "@/components/ui";

const MESSAGES: Record<string, string> = {
  expired: "Your GitHub sign-in expired. Sign in again to continue.",
  denied: "GitHub sign-in was cancelled.",
  state: "That sign-in link expired or was already used. Please try again.",
  github: "GitHub didn't complete the sign-in. Please try again.",
};

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <div className="mx-auto mt-16 max-w-sm">
      <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <h1 className="text-lg font-semibold">Sign in to Precedent</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Use your GitHub account. Precedent only reads who you are and which repositories you&apos;ve installed it
          on; it can&apos;t act as you.
        </p>
        <Suspense>
          <LoginForm searchParams={searchParams} />
        </Suspense>
      </div>
    </div>
  );
}

async function LoginForm({ searchParams }: { searchParams: PageProps<"/login">["searchParams"] }) {
  const params = await searchParams;
  const reason = [params.expired === "1" && "expired", typeof params.error === "string" && params.error].find(Boolean);
  const next = typeof params.next === "string" ? params.next : "/";
  return (
    <div className="mt-5 space-y-4">
      {reason && MESSAGES[reason as string] && (
        <p className="text-sm text-red-700 dark:text-red-400">{MESSAGES[reason as string]}</p>
      )}
      <GitHubButton href={`/auth/signin?next=${encodeURIComponent(next)}`} className="w-full justify-center">
        Sign in with GitHub
      </GitHubButton>
    </div>
  );
}
