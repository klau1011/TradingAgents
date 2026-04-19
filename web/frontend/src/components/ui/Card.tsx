import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  dark = false,
}: {
  children: ReactNode;
  className?: string;
  dark?: boolean;
}) {
  const surface = dark
    ? "bg-inverse text-inverse-fg"
    : "bg-canvas text-fg";
  return (
    <section className={`rounded-card ${surface} p-32p ${className}`}>
      {children}
    </section>
  );
}

export function SectionHeading({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2 className={`font-display text-section font-medium ${className}`}>
      {children}
    </h2>
  );
}
