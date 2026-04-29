import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Distinct CFO Copilot palette: deep ink + signal teal + premium gold
        ink: {
          950: "#070b14",
          900: "#0b1220",
          800: "#101a2e",
          700: "#1a2540",
          600: "#243153",
          500: "#324168",
        },
        signal: {
          DEFAULT: "#2dd4bf",
          50: "#ecfdf9",
          200: "#99f6e4",
          400: "#2dd4bf",
          500: "#14b8a6",
          600: "#0d9488",
        },
        gold: {
          DEFAULT: "#f4c66a",
          400: "#f4c66a",
          500: "#e6b14a",
        },
        danger: { DEFAULT: "#ef4444", soft: "#7f1d1d" },
        muted:  { DEFAULT: "#94a3b8" },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        ar: ["IBM Plex Sans Arabic", "Noto Sans Arabic", "system-ui"],
      },
      boxShadow: {
        glass: "0 1px 0 rgba(255,255,255,0.04) inset, 0 8px 30px rgba(0,0,0,0.35)",
        glow: "0 0 0 1px rgba(45,212,191,0.35), 0 0 22px rgba(45,212,191,0.15)",
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(ellipse at top, rgba(45,212,191,0.08), transparent 60%), radial-gradient(ellipse at bottom right, rgba(244,198,106,0.06), transparent 50%)",
      },
      animation: {
        "pulse-soft": "pulseSoft 2.4s ease-in-out infinite",
        "shimmer": "shimmer 2.2s linear infinite",
      },
      keyframes: {
        pulseSoft: {
          "0%,100%": { opacity: "0.55" },
          "50%":     { opacity: "1" },
        },
        shimmer: {
          "0%":   { backgroundPosition: "-400px 0" },
          "100%": { backgroundPosition: "400px 0" },
        },
      },
    },
  },
  plugins: [],
};
export default config;
