import { Suspense } from "react";

import { login } from "./actions";

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <div className="mx-auto mt-16 max-w-sm">
      <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <h1 className="text-lg font-semibold">Sign in to Precedent</h1>
        <p className="mt-1 text-sm text-zinc-500">Enter the dashboard password.</p>
        <Suspense>
          <LoginForm searchParams={searchParams} />
        </Suspense>
      </div>
    </div>
  );
}

async function LoginForm({ searchParams }: { searchParams: PageProps<"/login">["searchParams"] }) {
  const params = await searchParams;
  const failed = params.error === "1";
  const next = typeof params.next === "string" ? params.next : "/";

  return (
    <form action={login} className="mt-5 space-y-4">
      <input type="hidden" name="next" value={next} />
      <input
        type="password"
        name="password"
        required
        autoFocus
        autoComplete="current-password"
        placeholder="Password"
        aria-invalid={failed}
        className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
      />
      {failed && <p className="text-sm text-red-700 dark:text-red-400">That password is not right. Try again.</p>}
      <button
        type="submit"
        className="w-full rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
      >
        Sign in
      </button>
    </form>
  );
}
