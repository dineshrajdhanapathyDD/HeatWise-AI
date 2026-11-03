import type { ApiError } from "../api/client";

/** An error inside the block that failed, with a Retry text button (app-screens §11). */
export function BlockError({ what, error, onRetry }: { what: string; error: ApiError; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-card border border-line bg-surface p-5">
      <p className="text-body">
        <span className="font-medium">{`Couldn't load ${what}.`}</span> {error.message}
      </p>
      <button type="button" onClick={onRetry} className="mt-2 rounded-control text-body font-medium underline">
        Retry
      </button>
    </div>
  );
}
