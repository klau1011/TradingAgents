/** Tailwind config — encodes the DESIGN.md token system. */
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Primary surfaces
        dark: "#191c1f",
        surface: "#f4f4f4",
        // RUI semantic tokens
        rui: {
          blue: "#494fdf",
          "action-blue": "#4f55f1",
          "blue-text": "#376cd5",
          danger: "#e23b4a",
          "deep-pink": "#e61e49",
          warning: "#ec7e00",
          yellow: "#b09000",
          teal: "#00a87e",
          "light-green": "#428619",
          "green-text": "#006400",
          "light-blue": "#007bc2",
          brown: "#936d62",
          "red-text": "#8b0000",
        },
        // Neutral scale
        slate: {
          mid: "#505a63",
          cool: "#8d969e",
          tone: "#c9c9cd",
        },
      },
      fontFamily: {
        display: [
          "Aeonik Pro",
          "Inter",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
        body: ["Inter", "system-ui", "-apple-system", "sans-serif"],
      },
      // Type scale per DESIGN.md (size, line-height, letter-spacing)
      fontSize: {
        "display-mega": ["8.5rem", { lineHeight: "1.00", letterSpacing: "-2.72px" }],
        "display-hero": ["5rem", { lineHeight: "1.00", letterSpacing: "-0.8px" }],
        section: ["3rem", { lineHeight: "1.21", letterSpacing: "-0.48px" }],
        sub: ["2.5rem", { lineHeight: "1.20", letterSpacing: "-0.4px" }],
        card: ["2rem", { lineHeight: "1.19", letterSpacing: "-0.32px" }],
        feature: ["1.5rem", { lineHeight: "1.33", letterSpacing: "0px" }],
        nav: ["1.25rem", { lineHeight: "1.40", letterSpacing: "0px" }],
        "body-lg": ["1.125rem", { lineHeight: "1.56", letterSpacing: "-0.09px" }],
        body: ["1rem", { lineHeight: "1.50", letterSpacing: "0.24px" }],
        "body-em": ["1rem", { lineHeight: "1.50", letterSpacing: "0.16px" }],
      },
      borderRadius: {
        sm: "12px",
        card: "20px",
        pill: "9999px",
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
        focus: "0 0 0 0.125rem rgba(73, 79, 223, 0.45)",
      },
    },
  },
  plugins: [],
} satisfies Config;
