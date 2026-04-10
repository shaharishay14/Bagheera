# Backend Skill
FastAPI + SQLAlchemy + SQLite. Pydantic models match design §2.3 exactly.
Layout: app/main.py (lifespan starts worker thread, CORS localhost:5173), app/api/{inference,jobs,annotations,visualization}.py, app/db/{database,models}.py, app/workers/{queue_worker,mock_panther}.py, app/schemas.py.
Worker loop: fetch next Queued (priority ASC, created_at ASC) → Processing → mock_panther.run() sleeps 5-15s, 10% error → write clusters row → Done/Error. Sleep 1s when empty.
Reorder: 409 if any id not Queued; rewrite priority 0..N.
Rules: thin handlers, no compute in api/, uuid4().hex ids, HTTP codes per design (200/201/202), never import workers from api/.