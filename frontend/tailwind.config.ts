import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#111827",
        sidebar: "#172033",
        surface: "#1E293B",
        border: "#334155",
        primary: "#8B5CF6",
        secondary: "#22D3EE",
        ink: "#F1F5F9",
        muted: "#CBD5E1",
        success: "#10B981",
      },
      boxShadow: {
        card: "0 18px 40px rgb(2 6 23 / 0.22)",
      },
    },
  },
  plugins: [],
} satisfies Config;
