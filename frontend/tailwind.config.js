/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0f0f0f",
        surface: "#1a1a1a",
        border: "#2a2a2a",
        text: "#f0ede8",
        muted: "#8a8580",
        accent: "#e8c547",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        serif: ["Playfair Display", "Georgia", "serif"],
        sans: ["DM Sans", "Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
