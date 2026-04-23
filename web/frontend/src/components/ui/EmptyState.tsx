import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Friendly empty-state slot used when a list/feed has no items.
 * Provides an icon, headline, and optional secondary line + CTA slot.
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className = "",
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center py-12 px-6 ${className}`}
      role="status"
    >
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-pill bg-subtle/10 text-muted">
        <Icon size={28} strokeWidth={1.5} aria-hidden="true" />
      </div>
      <p className="font-display text-feature font-medium text-fg">{title}</p>
      {description && (
        <p className="mt-2 max-w-md text-body text-muted">{description}</p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
