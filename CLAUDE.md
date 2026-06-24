# Bagheera

A browser GUI for orchestrating the **TRIDENT** (feature extraction) and **PANTHER**
(prototype training) computational-pathology pipelines. Single-user, single-GPU.
FastAPI + SQLite backend, Vite + React + Tailwind frontend, async SQLite job queue.

Full context: [`docs/structure.md`](docs/structure.md) → [`docs/backend.md`](docs/backend.md)
→ [`docs/frontend.md`](docs/frontend.md) → [`docs/database.md`](docs/database.md)
→ [`docs/queue-design.md`](docs/queue-design.md) → [`docs/tests.md`](docs/tests.md)
→ [`docs/docker.md`](docs/docker.md)

---

## Architecture at a glance

```
browser → FastAPI (:8000) → SQLite (bagheera.db)
              │                   │
           routes/          worker thread
        (one per resource)  (polls jobs every 2s)
              │
         services/
    ┌─────────┴──────────┐
  fs.py          panther_train.py
  runner.py      post_train_viz.py
  splitter.py    inference_job.py
  worker.py      visualization.py
```

Frontend (`frontend/src/`): `App.tsx` → pages → components → `lib/api.ts` (typed
fetch wrapper, the FE↔BE contract). Vite proxies `/api/*` to `:8000` in dev.

---

## Dev commands

```bash
# Backend
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm run dev          # :5173

# Seed demo data
cd backend && python scripts/seed_demo.py

# Tests
cd backend && pytest -v
cd frontend && npm run test

# Wipe + recreate DB
rm backend/bagheera.db && uvicorn app.main:app --reload

# Docker (GPU machine) — see docs/docker.md
cp .env.example .env                 # fill in WSI_DATA_DIR, STATE_DIR, CUDA tag
docker compose build && docker compose up -d   # UI at http://localhost:8080
```

---

## The agents

Each agent reads its doc file **in full** before acting — treat the doc as the source
of truth. Update the doc in the same change as any code it governs.

| Agent | Invoke with | Doc it owns | When to use |
| --- | --- | --- | --- |
| `backend` | `@backend` | `docs/backend.md` + `queue-design.md` | Routes, services, worker, job handlers, config |
| `frontend` | `@frontend` | `docs/frontend.md` | React pages, components, design system |
| `database` | `@database` | `docs/database.md` | Schema changes, new tables/columns/indexes |
| `structure` | `@structure` | `docs/structure.md` | Architecture questions, cross-cutting concerns |
| `tests` | `@tests` | `docs/tests.md` | Write, scaffold, and run tests |

**Frontend work** always goes through the `@frontend` agent, which invokes the
`frontend-design` skill for visual changes and uses the shared design-system tokens
(`src/index.css`, `tailwind.config.js`, `src/components/ui/`).

---

## Hard conventions

| Rule | Why |
| --- | --- |
| **No DB migrations** — delete `bagheera.db` after schema changes | No migration framework in the stack; `create_all()` is the schema lifecycle |
| **`ALTER TABLE` guard for additive columns** — add in `init_db()` | Lets new columns survive existing DBs without a wipe |
| **Every path through `resolve_within_roots()`** | The only security boundary; blocks traversal and symlink escape |
| **Lazy ML imports** — `torch`, `openslide`, `h5py` inside functions only | Server must boot on a dev laptop without GPU deps |
| **Worker never crashes** — all handler exceptions caught and logged | One failure must not stop the queue processing future jobs |
| **Polling, not websockets** — 2 s `setTimeout` loops | Keeps the frontend dependency-light; `JobStatusPoller` is the standard |
| **`resolveVizUrl` for every viz image** | Degrades to labeled SVG placeholders during pending/rendering states |
| **`lib/api.ts` first** — types + function before any page uses an endpoint | Single source of truth for the FE↔BE contract |
| **Design tokens only** — `bg-accent`, `text-ink`, `border-border`, `shadow-card` | No hardcoded `bg-slate-900` / `bg-white` for structural UI elements |
