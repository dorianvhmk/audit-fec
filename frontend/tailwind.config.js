/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        gold: {
          DEFAULT: "#C9A84C",
          light:   "#D4B86A",
          dim:     "#C9A84C26",
        },
        surface: {
          DEFAULT: "#141414",
          raised:  "#1C1C1C",
        },
        edge: "#252525",
        ink: {
          DEFAULT: "#E8E8E8",
          muted:   "#888888",
          faint:   "#444444",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
