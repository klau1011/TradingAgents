import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "outlined" | "ghost";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

const base =
  "font-display text-nav font-medium rounded-pill transition-opacity " +
  "focus:outline-none focus-visible:shadow-focus disabled:opacity-40 disabled:cursor-not-allowed";

const variants: Record<Variant, string> = {
  primary: "bg-dark text-white px-32p py-14p hover:opacity-85",
  secondary: "bg-surface text-black px-34p py-14p hover:opacity-85",
  outlined:
    "bg-transparent text-dark border-2 border-dark px-32p py-14p hover:opacity-85",
  ghost:
    "bg-white/10 text-surface border-2 border-surface px-32p py-14p hover:opacity-85",
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
