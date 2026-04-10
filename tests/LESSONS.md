# Bagheera — Test Lessons & Future Work

## Monitoring notes (design §9)

- **User-facing monitoring** lives in the GUI's Jobs Dashboard: every job row
  shows status, start/finish timestamps, and any error string. This is the
  primary surface pathologists use to spot stuck or failed runs — no
  separate ops console.
- **System troubleshooting** relies on standard Python file logging. The
  worker thread logs every claim, every mock-PANTHER exception, and any
  unexpected loop failure with `logger.exception(...)`. The design's
  guidance is that isolated errors must not require a full restart, so the
  worker loop catches and logs broad exceptions and keeps polling.
- **Test results** are written by `tests/conftest.py::pytest_sessionfinish`
  to `tests/results/run-<utc>.json`. Each run contains pass/fail counts,
  per-test durations, and the test ids — we keep a directory rather than a
  single file so historical runs accumulate without merge conflicts.

## What we deliberately deferred (and why)

- **Real PANTHER integration.** MVP mocks the model in
  `backend/app/workers/mock_panther.py`. The interface is a single
  `run(num_clusters)` function that returns cluster outputs (or raises) so
  swapping in the real Harvard PANTHER pipeline is a single-file change
  plus dependency installation.
- **Split Execution / Result workers** (design §5). The design specifies
  two cooperating loops; we collapse them into one thread because the mock
  finishes synchronously and a split would not exercise any new code paths.
  When PANTHER goes live, split this so the Execution worker can fire
  multiple jobs at the GPU before any one completes.
- **Authentication / authorization.** No login wall. On-prem deployment
  inside Sheba's intranet means we can defer this to a reverse proxy
  (e.g. SSO header forwarding) until the security review.
- **Real WSI viewer.** No OpenSeadragon / DeepZoom yet — `clusters`
  responses currently return mock patch paths. The visualization endpoint
  shape (`{clusters:[{cluster_id, patches:[...]}]}`) matches the design so
  the frontend viewer can be added without an API change.
- **File uploads + H5/PT ingestion.** The MVP takes a path string only;
  `POST /api/v1/datasets/upload` from design §2.3 is intentionally not
  implemented. Add a multipart endpoint + a storage abstraction
  (`backend/app/storage/`) once the Sheba data team confirms whether files
  land on a shared mount, hospital object storage, or PACS.
- **Alembic migrations.** The MVP uses `Base.metadata.create_all` on
  startup. As soon as the schema needs to change against an existing
  database, generate an initial Alembic revision and gate further changes
  through it.
- **Persistent job progress.** `progress` is currently derived
  (Queued=0, Processing=50, Done/Error=100). The real PANTHER worker
  should write granular progress (e.g. `% patches processed`) to a
  dedicated column.
- **Structured logging + metrics endpoint.** Plain Python logging is
  enough for now; add `prometheus_client` and a `/metrics` route when
  on-call needs throughput / queue-depth dashboards.

## Things we learned writing the tests

- **TC-02 in unit tests** is simulated by flipping a job's status to
  `Processing` directly in the DB rather than waiting for the worker —
  this keeps the unit suite deterministic and fast.
- **Integration test for reorder** needed a "sentinel" Processing row to
  hold the queue while we submitted and reordered jobs. Without this hold
  the worker would race the test and start jobs in submission order before
  the reorder PUT landed.
- **Mock sleep** is shrunk to 0.05–0.15 s in `client_with_worker` so the
  full integration suite finishes in seconds, not minutes.
