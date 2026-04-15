/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      colors: {
        surface: {
          0: "#ffffff",
          1: "#f8f9fa",
          2: "#f1f3f5",
          3: "#e9ecef",
        },
        border: {
          DEFAULT: "#dee2e6",
          strong: "#ced4da",
        },
        text: {
          primary: "#212529",
          secondary: "#495057",
          muted: "#868e96",
        },
        accent: {
          DEFAULT: "#1c7ed6",
          hover: "#1971c2",
          light: "#e7f5ff",
        },
        danger: {
          DEFAULT: "#e03131",
          light: "#fff5f5",
        },
        success: {
          DEFAULT: "#2f9e44",
          light: "#ebfbee",
        },
      },
    },
  },
  plugins: [],
};
