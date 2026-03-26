/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./features/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        steel: "#334155",
        sand: "#f6f0e1",
        brass: "#b6862c",
        mist: "#dbe6ef",
        pine: "#16423c",
      },
      boxShadow: {
        panel: "0 18px 60px rgba(15, 23, 42, 0.12)",
      },
      backgroundImage: {
        "legal-grid":
          "linear-gradient(rgba(15,23,42,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.06) 1px, transparent 1px)"
      }
    },
  },
  plugins: [],
};
