import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "outlined" | "ghost" | "danger";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center gap-2 font-display text-body font-medium rounded-pill border px-5 py-2.5 transition-opacity " +
  "focus:outline-none focus-visible:shadow-focus disabled:opacity-40 disabled:cursor-not-allowed";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-accent-ink border-accent hover:opacity-85",
  secondary: "bg-surface text-fg border-edge-strong hover:opacity-85",
  outlined: "bg-transparent text-fg border-edge-strong hover:opacity-85",
  // Ghost is for the deep hero bands (bg-inverse): a panel-step fill lifts
  // it off the band.
  ghost: "bg-surface text-fg border-edge-strong hover:opacity-85",
  danger: "bg-bad-soft text-bad border-bad/40 hover:opacity-85",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  ...rest
}: Props) {
  return (
    <button {...rest} className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}
