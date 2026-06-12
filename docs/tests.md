# Bagheera — Testing Strategy

> No tests existed when this file was created. This document defines the testing
> approach so that every agent and contributor starts from the same page.

---

## 1. Philosophy

- **Test the logic, not the wiring.** Pure service functions (path resolution,
  K-fold split invariants, hash computation, queue CAS) are the highest-value targets.
  HTTP route tests come second.
- **Isolated state.** Every backend test gets its own temp SQLite DB (`tmp_path` +
  `create_all()`). No shared mutable state between tests.
- **No GPU, no ML deps in tests.** The heavy imports (`torch`, `openslide`, `h5py`,
  `umap`, `matplotlib`) are lazy; tests must never trigger them. Mock subprocess
  calls; don't run TRIDENT or PANTHER.

---

## 2. Backend — pytest

### Setup

```bash
cd backend
pip install pytest pytest-anyio httpx  # add to requirements-dev.txt
pytest                                  # runs all tests under backend/tests/
```

### File layout

```
backend/
└── tests/
    ├── conftest.py          # shared fixtures: in-memory DB, TestClient
    ├── test_fs.py           # resolve_within_roots sandbox
    ├── test_splitter.py     # K-fold invariants
    ├── test_preview.py      # deterministic slide picking
    ├── test_inference.py    # hash, cache lookup, path helpers
    ├── test_queue.py        # CAS claim / cancel / reorder
    └── test_routes_*.py     # HTTP-level smoke tests (one file per router)
```

### `conftest.py` pattern

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db.database import Base
from app.main import app, get_db

@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()

@pytest.fixture()
def client(db):
    def override(): yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

### Priority test cases

| Module | What to assert |
| --- | --- |
| `services/fs.py` | `resolve_within_roots` raises 403 for paths outside roots; accepts paths inside; resolves `..` traversal to the root or rejects. |
| `services/splitter.py` | K-fold invariant: every slide in `test` exactly once across K folds; train+val+test = all slides per fold; count per fold is consistent with `per_fold_counts`. |
| `services/preview.py` | Same `(model_id, seed, fold_index)` always returns the same slides (determinism); returns at most `count` slides; handles CSVs with `slide_id`, `case_id`, `slide`, `id` columns. |
| `services/inference.py` | `compute_wsi_hash` is stable across calls; `lookup_cached_inference` returns hit on matching hash, None on miss; `build_trident_command` produces expected argv. |
| Queue (worker + routes) | Claim CAS: worker claims lowest `queue_position` queued job; if status changed to `canceled` between select and update, claim returns 0 rows and moves on. Cancel CAS: `status='canceled'` update returns 0 rows if job already `running` → 409. Reorder: positions rewritten atomically; jobs that changed status mid-reorder are ignored. |

---

## 3. Frontend — Vitest + React Testing Library

### Setup

```bash
cd frontend
npm install --save-dev vitest @testing-library/react @testing-library/user-event jsdom
# add to vite.config.ts: test: { environment: 'jsdom' }
npm run test
```

### What to test

- **`lib/api.ts`** — `resolveVizUrl` fallback logic; `request` error parsing.
- **`components/ui/StatusPill`** — renders correct label and color class for each status.
- **Pure helpers** in pages (e.g. `moveBefore` in QueuePage, `pctLabel` in PantherForm).

Integration tests (mount + mock fetch) for interactive components come after unit
coverage is solid.

---

## 4. Running everything

```bash
# Backend
cd backend && pytest -v

# Frontend
cd frontend && npm run test

# Both (from repo root)
(cd backend && pytest) && (cd frontend && npm run test)
```

---

## 5. Conventions

- **New endpoint or service function** → ship a test in the same PR.
- **Bug fix** → add a regression test that would have caught it.
- **No `sleep()` in tests** — use `TestClient` (sync) or mock time.
- **No real filesystem paths** — use `tmp_path` (pytest) or `tmp_dir` (vitest).
- **No subprocess calls** — mock `subprocess.Popen` / `subprocess.run` at the
  `services.runner` / `services.panther_runner` import level.

> Keep this file in sync when you add test modules or change the test infrastructure.
