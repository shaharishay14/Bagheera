# Static assets (`frontend/public/`)

Anything in this folder is served at the site root by Vite (e.g. `public/foo.svg`
→ `/foo.svg`) and copied verbatim into the production build. No code changes are
needed — just drop a file in with the exact name below and it appears.

## Current assets (filenames are referenced by exact name in code)

| File | Where it shows | Fallback if missing |
| --- | --- | --- |
| `bagheera_logo.png` | Navbar (all pages), landing hero, footer | gradient "B" mark + "Bagheera" text |
| `mahmood_logo.png` | Landing → "Powered by" section | "Mahmood Lab" text card |
| `harvard_logo.png` | Landing → "Powered by" section | "Harvard / Medical School" text card |

Each degrades to a clean text fallback, so the app looks fine even if a file is removed.

## Optional / not needed

- **Tech-stack logos** (React, FastAPI, Python, Docker, SQLite, Vite, Tailwind) —
  rendered from the `react-icons` package, no files required.
- **TRIDENT / PANTHER** — shown as styled text badges; only add files if you have
  official marks (then wire them in `src/pages/LandingPage.tsx`).
- **Docker ↔ PC diagram** — built from icons + SVG, no image files required.
- **favicon** — optional; drop `favicon.svg`/`favicon.ico` here and reference it in
  `index.html` if you want to replace the default tab icon.
