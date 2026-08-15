/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./skill_vault/web/templates/**/*.html",
    "./skill_vault/web/static/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic tokens wired to the CSS custom properties in skillvault.css
        // via rgb(var(--sv-*) / <alpha-value>) so utility classes honour dark mode.
        bg: "rgb(var(--sv-bg) / <alpha-value>)",
        surface: "rgb(var(--sv-surface) / <alpha-value>)",
        line: "rgb(var(--sv-border) / <alpha-value>)",
        ink: "rgb(var(--sv-text) / <alpha-value>)",
        mute: "rgb(var(--sv-muted) / <alpha-value>)",
        brand: "rgb(var(--sv-primary) / <alpha-value>)",
        accent: "rgb(var(--sv-accent) / <alpha-value>)",
        // Trust-tier accent colours (card borders / filter chips).
        verified: "rgb(var(--sv-verified) / <alpha-value>)",
        "user-tier": "rgb(var(--sv-user) / <alpha-value>)",
        "public-tier": "rgb(var(--sv-public) / <alpha-value>)",
      },
    },
  },
  plugins: [],
};
