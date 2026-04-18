# Database Skill
SQLite bagheera.db at repo root, SQLAlchemy ORM, auto-create tables on startup (no Alembic for MVP).
All datetime columns use the UTCDateTime TypeDecorator (backend/app/db/types.py) — round-trips with tzinfo=UTC attached on every load.

## Tables
- jobs(id str pk, dataset_id, num_clusters, status, priority int, created_at UTCDateTime, started_at?, finished_at?, error?, encoder str default "uni", em_iter int default 1, tau float default 1.0, out_type str default "allcat")
- annotations(id str pk, target_id, target_type, note text, created_at UTCDateTime)
- clusters(id str pk, job_id fk, label?, patches_json text, prototype_index int default 0)

## Status
Queued|Processing|Done|Error. FIFO: ORDER BY priority ASC, created_at ASC.

## Rules
Session via Depends(get_db). Worker wraps fetch+status-update in BEGIN IMMEDIATE transaction. Reorder: listed jobs get priorities 0..N-1; unlisted Queued jobs follow (N..) in their original FIFO order; all in one transaction. Store only paths, never binaries. Delete `backend/bagheera.db` when adding new non-nullable columns (tests use a fresh temp DB automatically).
