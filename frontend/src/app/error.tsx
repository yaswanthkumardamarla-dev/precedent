"use client";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
      <p className="font-medium">Something went wrong loading this page.</p>
      <p className="mt-1">{error.message}</p>
      <button
        onClick={reset}
        className="mt-4 rounded-md bg-red-900 px-3 py-1.5 text-white hover:bg-red-800 dark:bg-red-200 dark:text-red-950"
      >
        Try again
      </button>
    </div>
  );
}
