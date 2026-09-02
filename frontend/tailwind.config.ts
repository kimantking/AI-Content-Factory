import type { Config } from "tailwindcss";

/**
 * AI Content Factory design tokens.
 * Values map 1:1 to /DESIGN.md (Linear near-black system). Colors resolve to CSS
 * custom properties defined in app/globals.css so the dark (default) and light
 * themes swap without utility churn. Dark is the reference implementation.
 */
const rgb = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: rgb("--primary"),
        "primary-hover": rgb("--primary-hover"),
        "primary-focus": rgb("--primary-focus"),
        "on-primary": rgb("--on-primary"),
        ink: rgb("--ink"),
        "ink-muted": rgb("--ink-muted"),
        "ink-subtle": rgb("--ink-subtle"),
        "ink-tertiary": rgb("--ink-tertiary"),
        canvas: rgb("--canvas"),
        "surface-1": rgb("--surface-1"),
        "surface-2": rgb("--surface-2"),
        "surface-3": rgb("--surface-3"),
        "surface-4": rgb("--surface-4"),
        "hairline-strong": rgb("--hairline-strong"),
        success: rgb("--success"),
        "brand-secure": rgb("--brand-secure"),
        // single-knob hairline (opacity baked via --hairline-o); no /alpha variants
        hairline: "rgb(var(--hairline) / var(--hairline-o))",
      },
      borderRadius: {
        // DESIGN.md rounded scale
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        xxl: "24px",
      },
      spacing: {
        // DESIGN.md spacing scale (4px base). section rhythm token.
        section: "96px",
      },
      fontFamily: {
        display: "var(--font-display)",
        sans: "var(--font-text)",
        mono: "var(--font-mono)",
      },
      fontSize: {
        // DESIGN.md typography table -> [size, {lineHeight, letterSpacing}]
        "display-xl": ["80px", { lineHeight: "1.05", letterSpacing: "-3px", fontWeight: "600" }],
        "display-lg": ["56px", { lineHeight: "1.1", letterSpacing: "-1.8px", fontWeight: "600" }],
        "display-md": ["40px", { lineHeight: "1.15", letterSpacing: "-1px", fontWeight: "600" }],
        headline: ["28px", { lineHeight: "1.2", letterSpacing: "-0.6px", fontWeight: "600" }],
        "card-title": ["22px", { lineHeight: "1.25", letterSpacing: "-0.4px", fontWeight: "500" }],
        subhead: ["20px", { lineHeight: "1.4", letterSpacing: "-0.2px" }],
        "body-lg": ["18px", { lineHeight: "1.5", letterSpacing: "-0.1px" }],
        body: ["16px", { lineHeight: "1.5", letterSpacing: "-0.05px" }],
        "body-sm": ["14px", { lineHeight: "1.5" }],
        caption: ["12px", { lineHeight: "1.4" }],
        eyebrow: ["13px", { lineHeight: "1.3", letterSpacing: "0.4px", fontWeight: "500" }],
      },
      maxWidth: {
        workspace: "1240px",
      },
    },
  },
  plugins: [],
};
export default config;
