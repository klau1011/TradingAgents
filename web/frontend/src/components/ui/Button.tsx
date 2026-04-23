import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "outlined" | "ghost" | "danger";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center gap-2 font-display text-nav font-medium rounded-pill transition-opacity " +
  "focus:outline-none focus-visible:shadow-focus disabled:opacity-40 disabled:cursor-not-allowed";

const variants: Record<Variant, string> = {
  primary: "bg-inverse text-inverse-fg px-32p py-14p hover:opacity-85",
  secondary: "bg-surface text-fg px-34p py-14p hover:opacity-85",
  outlined:
    "bg-transparent text-fg border-2 border-fg px-32p py-14p hover:opacity-85",
  // Ghost is for use on inverted hero sections (bg-inverse). Colors track
  // the hero's foreground (inverse-fg) so it inverts cleanly with the theme.
  ghost:
    "bg-inverse-fg/10 text-inverse-fg border-2 border-inverse-fg px-32p py-14p hover:opacity-85",
  danger:
    "bg-rui-danger text-white border-2 border-rui-danger px-32p py-14p hover:opacity-85",
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
