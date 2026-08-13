# Queue — Design & Implementation Notes

A real, shared job queue with FIFO default, cancel, drag-to-reorder, and
multi-user concurrency, built on the existing SQLite `jobs` table + single
worker thread (no Redis/Celery). See [backend.md](./backend.md) and
[structure.md](./structure.md) for the surrounding system.

## Decisions (locked with the product owner)

- **One shared queue, many users, one job on the GPU at a time** (the single
  worker thread *is* the GPU serialization — kept as-is).
- **Cancel** applies to **waiting jobs only**; a running job is left to finish
  (we never kill a running subprocess).
- **Reorder** applies to **waiting jobs only**, via click-and-drag.
- **Re-run** a `failed` / `canceled` (and `succeeded`) job → it re-enters at the
  **back** of the queue.
- **Shared control:** anyone can cancel / reorder / re-run any job (no auth).
- Keep per-job logs and per-fold images; cleanup is out of scope here.

## Data model (`jobs` table)

- **`queue_position: int | null`** — order among waiting jobs (lower runs
  sooner). Set on enqueue (FIFO) / re-run (tail). `NULL` once a job leaves the
  queue. Backfilled on existing DBs via an `ALTER TABLE` guard in `init_db`
  (no migration framework).
- **status gains `canceled`** (terminal). `finished_at` stamps the cancel time.

## Concurrency model — compare-and-swap

All correctness rests on conditional updates; the DB picks the winner of any
race, so no application locks are needed.

1. **Claim (worker):** select the lowest-position queued job, then
   `UPDATE … SET status='running' WHERE id=:id AND status='queued'`. If 0 rows
   change (a user cancelled it first), skip to the next.
2. **Cancel (user):** `UPDATE … SET status='canceled' WHERE id=:id AND
   status='queued'`. 0 rows → **409** ("already started").
3. **Reorder (user):** atomic full-order rewrite — the client sends the desired
   order of waiting jobs; the server rewrites `queue_position` for those still
   queued in one transaction, ignoring any that have since started/cancelled.

**SQLite tuning:** WAL mode + `busy_timeout=5000` so many concurrent pollers
(reads) and the occasional write don't hit "database is locked."

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/queue` | `{ running, waiting[], recent[] }` with server-resolved title/subtitle per job. |
| POST | `/api/jobs/{id}/cancel` | Cancel a waiting job (CAS). 409 if not queued. |
| POST | `/api/queue/reorder` | Body `{ ordered_job_ids }` → atomic position rewrite. |
| POST | `/api/jobs/{id}/retry` | Re-run a terminal job → fresh tail position. |

## Worker

- Claim orders by `queue_position, created_at`; CAS claim; skip-on-lost-race.
- Clears `queue_position` on claim. One-at-a-time execution unchanged.
- No running-job cancellation (by decision) → no cancel-flag polling.

## Frontend — `/queue` page

- Polls `GET /api/queue` every 2 s. Server is the source of truth.
- **Now running** card (log link, elapsed; no cancel). **Waiting** list:
  draggable rows (native HTML5 DnD, zero deps) with position + **Cancel**.
  **Recent** (collapsible): `succeeded`/`failed`/`canceled` with log + **Re-run**.
- **Freeze during drag:** skip applying poll updates while a drag is in
  progress so the row under the cursor doesn't jump; reconcile on drop.
- Optimistic reorder → POST `/api/queue/reorder` → reconcile on next poll.
  Cancel returning 409 → inline "already started" notice.

## Verification (concurrency)

Two browser tabs, force the races:
- **cancel vs. reorder:** one tab drags while the other cancels — queue stays
  consistent (no ghost/dup, sane order).
- **cancel vs. start:** cancel a job the instant the worker claims it — exactly
  one wins (409 + runs, or never starts); never both.
