# Bagheera — Testing Strategy

The formal deliverables live in [`docs/tests/STP_STD - Bagheera.docx`](tests/) —
a combined Software Test Plan and Software Test Design. That document is the
contract; this file is the working guide for writing and running the suite.

**Current state:** 474 backend cases and 248 frontend cases, all passing.
Combined runtime is about 15 seconds.

**Scope:** Bagheera trains **one model on the entire dataset**. The UI posts
`kind: "single"` to `/api/splits` and then hits `/api/panther/single-runs`, so
that is the path the suite covers.

---

## 1. Philosophy

- **Test the logic, not the wiring.** Pure service functions (path resolution,
  split integrity, hash computation, queue CAS) are the highest-value targets.
  HTTP route tests come second.
- **Isolated state.** Every backend test gets its own temp SQLite DB (`tmp_path` +
  `create_all()`). No shared mutable state between tests.
- **No GPU, no ML deps in tests.** The heavy imports (`torch`, `openslide`, `h5py`,
  `umap`, `matplotlib`) are lazy; tests must never trigger them. Mock subprocess
  calls; don't run TRIDENT or PANTHER. `test_app.py` asserts this directly.
- **Negative cases carry equal weight.** For the sandbox and the queue, the
  refusal paths *are* the product.

---

## 2. Backend — pytest

```bash
cd backend && pytest -v
```

### File layout

```
backend/tests/
├── conftest.py                  # db, client, override_settings fixtures
├── test_app.py                  # bootstrap, routers, CORS, config parsing, lazy-import guard
├── test_fs.py                   # resolve_within_roots sandbox + /api/fs
├── test_preview.py              # CSV id-column detection, deterministic preview picking
├── test_splitter.py             # the training split
├── test_panther_runner.py       # split paths, feats_h5 shim, argv
├── test_inference_service.py    # hashing, cache verification, TRIDENT argv
├── test_worker.py               # handler registry, claim CAS, job execution, logs
├── test_assignment_cache.py     # LRU cache
├── test_model_delete.py         # FK-safe cascade + guarded disk cleanup
└── test_routes_*.py             # one file per router
```

### Shared fixtures (`conftest.py`)

| Fixture | What it gives you |
| --- | --- |
| `db` | A session on a fresh temp SQLite file built with `create_all()` |
| `client` | `TestClient(app)` with `get_db` overridden to `db`. **No lifespan** — the background worker never starts |
| `override_settings` | `override_settings(allowed_roots=[...], viz_cache_root=...)`. Writes through the frozen dataclass and restores every touched attribute at teardown |

```python
def test_something(client, db, tmp_path, override_settings):
    override_settings(allowed_roots=[tmp_path])
    assert client.get("/api/fs/roots").json()["roots"] == [str(tmp_path)]
```

### Gotchas worth knowing

- **Bulk deletes bypass the identity map.** After a route issues
  `query(...).delete()`, call `db.expunge_all()` before `db.get(...)`, and capture
  ids as plain strings *before* the request — a commit expires the ORM instances
  and touching `.id` on a deleted row raises.
- **`inferences` has `UNIQUE(model_id, wsi_hash)`.** Rows are created with an
  empty placeholder hash, so a model can hold only one un-dispatched inference
  at a time. Give each inference in a test a distinct slide, or a distinct
  model, or the insert will collide.
- **Training writes no `model_groups` row.** `/api/panther/single-runs` sets
  `group_id == model_id` and enqueues `panther_train` with `ref_table="models"`,
  so anything that resolves a training job through `model_groups` will miss.

---

## 3. Frontend — Vitest + React Testing Library

```bash
cd frontend && npm run test        # vitest run
npx tsc -b                         # typecheck
```

### File layout

```
frontend/src/
├── lib/api.test.ts               # slideThumbnailUrl
├── lib/api.contract.test.ts      # request wrapper, error translation, viz URL resolution
├── components/ui/ui.test.tsx     # Button, Card, Chip, Field, SectionHeader, StatusPill
├── components/*.test.tsx         # JobStatusPoller, JobLogViewer, ConfirmDeleteModal,
│                                 # DirectoryBrowser, NotesThread, PrototypeLabels,
│                                 # EncoderSelect, PantherForm, ZoomPanImage
└── pages/*.test.ts(x)            # QueuePage helpers, PantherComparePage
```

### Conventions

- **`afterEach(cleanup)` in every file.** Auto-cleanup is not registered because
  `globals` is off in `vite.config.ts`; without it, renders accumulate in the
  same document and `getByRole` finds duplicates.
- **Mock `../lib/api`, not `fetch`,** for component tests:
  ```ts
  vi.mock('../lib/api', async () => {
    const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api');
    return { ...actual, listJobs: (...a: unknown[]) => listJobs(...a) };
  });
  ```
  Spread `actual` so `ApiError` stays the real class — components branch on
  `instanceof ApiError`.
- **Query by role and accessible name.** `getByRole('button', { name: 'Delete' })`
  over class or test-id selectors.
- **Polling components need fake timers.** Assert both that they poll *and* that
  they stop:
  ```ts
  vi.useFakeTimers();
  render(<JobStatusPoller refId="g-1" />);
  await act(async () => {});
  await act(async () => { vi.advanceTimersByTime(2000); });
  ```

### Three traps that cost real time

1. **Never leave a promise unsettled.** `mockReturnValue(new Promise(() => {}))`
   for a loading state hangs the jsdom teardown. Use a deferred you resolve
   before the test ends.
2. **`mockRejectedValue` builds the rejected promise eagerly**, which registers
   as an unhandled rejection before the component consumes it. Use
   `mockImplementation(() => Promise.reject(err))`.
3. **Hooks must not return a value.** `beforeEach(() => mock.mockReset())` returns
   the mock, which vitest then calls as the teardown function. Use a block body.
4. **jsdom has no layout engine.** Stub `Element.prototype.scrollIntoView` for
   anything with a keyboard-driven highlight.

---

## 4. Running everything

```bash
(cd backend && pytest) && (cd frontend && npm run test && npx tsc -b)
```

---

## 5. Conventions

- **New endpoint or service function** → ship a test in the same PR, and add the
  matching test case to the STD.
- **Bug fix** → add a regression test that would have caught it.
- **No `sleep()`** — `TestClient` is synchronous; use fake timers on the frontend.
- **No real filesystem paths** — `tmp_path` (pytest) or per-test fixtures (vitest).
- **No subprocess calls** — mock `services.runner.execute` /
  `services.panther_runner.execute` at the module level.

> Keep this file and the STD in sync when you add test modules or change the
> test infrastructure.
