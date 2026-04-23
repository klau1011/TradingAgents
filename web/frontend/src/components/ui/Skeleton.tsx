import type { ReactNode } from "react";

/**
 * Pulse-animated placeholder block. Pure presentational — accepts arbitrary
 * Tailwind sizing via `className`.
 */
export function Skeleton({
  className = "",
  rounded = "rounded-card",
}: {
  className?: string;
  rounded?: string;
}) {
  return (
    <div
      className={`bg-subtle/15 motion-safe:animate-pulse ${rounded} ${className}`}
      aria-hidden="true"
    />
  );
}

export function SkeletonText({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          rounded="rounded-pill"
          className={`h-3 ${i === lines - 1 ? "w-2/3" : "w-full"}`}
        />
      ))}
    </div>
  );
}

/** Common building block: a table row of skeleton cells. */
export function SkeletonTable({
  rows = 4,
  cols = 4,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          className="grid gap-4"
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton
              key={c}
              rounded="rounded-pill"
              className="h-4"
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Convenience wrapper: a "card-shaped" loading placeholder. */
export function SkeletonCard({ children }: { children?: ReactNode }) {
  return (
    <div className="bg-canvas rounded-card p-32p space-y-4">
      {children ?? (
        <>
          <Skeleton className="h-6 w-1/3" rounded="rounded-pill" />
          <SkeletonText lines={4} />
        </>
      )}
    </div>
  );
}
