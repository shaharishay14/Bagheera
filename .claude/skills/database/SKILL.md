# Database Skill
SQLite bagheera.db at repo root, SQLAlchemy ORM, auto-create tables on startup (no Alembic for MVP).
Tables:
- jobs(id str pk, dataset_id, num_clusters, status, priority int, created_at, started_at?, finished_at?, error?)
- annotations(id str pk, target_id, target_type, note text, created_at)
- clusters(id str pk, job_id fk, label?, patches_json text)
Status: Queued|Processing|Done|Error. FIFO: ORDER BY priority ASC, created_at ASC.
Rules: Session via Depends(get_db). Worker wraps fetch+status-update in BEGIN IMMEDIATE transaction. Reorder in single transaction after validating all ids are Queued. Store only paths, never binaries.