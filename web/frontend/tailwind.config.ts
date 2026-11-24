/** Tailwind config — encodes the DESIGN.md token system. */
import type { Config } from "tailwindcss";

// Tokens are OKLCH channels in tokens.css; <alpha-value> keeps `/60` modifiers working.
const token = (name: string) => `oklch(var(--color-${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: token("bg"),
        fg: token("fg"),
        muted: token("muted"),
        subtle: token("subtle"),
        edge: { DEFAULT: token("border"), strong: token("border-strong") },
        surface: token("surface"),
        // Deepest graphite step: hero bands, code and inputs.
        inverse: token("inverse"),
        "inverse-fg": token("inverse-fg"),
        accent: {
          DEFAULT: token("accent"),
          ink: token("accent-ink"),
          soft: token("accent-soft"),
        },
        cool: { DEFAULT: token("cool"), soft: token("cool-soft") },
        ok: { DEFAULT: token("ok"), soft: token("ok-soft") },
        bad: { DEFAULT: token("bad"), soft: token("bad-soft") },
      },
      fontFamily: {
        display: ["Host Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        body: ["Host Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["Atkinson Hyperlegible Mono", "ui-monospace", "monospace"],
      },
      // Type scale per DESIGN.md (size, line-height, letter-spacing)
      fontSize: {
        "display-mega": ["8.5rem", { lineHeight: "1.02", letterSpacing: "-0.03em" }],
        "display-hero": ["5rem", { lineHeight: "1.04", letterSpacing: "-0.03em" }],
        section: ["3rem", { lineHeight: "1.04", letterSpacing: "-0.03em" }],
        sub: ["2.5rem", { lineHeight: "1.05", letterSpacing: "-0.03em" }],
        card: ["2rem", { lineHeight: "1.1", letterSpacing: "-0.03em" }],
        feature: ["1.5rem", { lineHeight: "1.33", letterSpacing: "0px" }],
        nav: ["1.25rem", { lineHeight: "1.40", letterSpacing: "0px" }],
        "body-lg": ["1.125rem", { lineHeight: "1.55", letterSpacing: "0px" }],
        body: ["1rem", { lineHeight: "1.55", letterSpacing: "0px" }],
        "body-em": ["1rem", { lineHeight: "1.55", letterSpacing: "0px" }],
      },
      borderRadius: {
        chip: "4px",
        sm: "6px",
        card: "10px",
        // Name kept from the old pill buttons; Console controls are 6px.
        pill: "6px",
      },
      spacing: {
        "14p": "14px",
        "32p": "32px",
        "34p": "34px",
        "80p": "80px",
        "88p": "88px",
        "120p": "120px",
      },
      // Disable shadows entirely — DESIGN.md mandates flat surfaces.
      boxShadow: {
        focus: "0 0 0 2px oklch(var(--color-accent) / 0.6)",
      },
    },
  },
  plugins: [],
} satisfies Config;
