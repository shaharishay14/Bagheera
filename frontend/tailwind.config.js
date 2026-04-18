/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        panther: {
          950: "#080F1A",
          900: "#0D1B2A",
          800: "#152236",
          700: "#1C3050",
          600: "#243B62",
          400: "#4A7EB5",
          200: "#A8C4E0",
          50: "#EEF4FB",
        },
        accent: {
          DEFAULT: "#C8102E",
          hover: "#A50D25",
          light: "#FDEAED",
        },
      },
      fontFamily: {
        display: ['"Playfair Display"', "Georgia", "serif"],
        body: ['"DM Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"Fira Code"', "monospace"],
      },
    },
  },
  plugins: [],
};
