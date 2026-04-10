import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import annotations, inference, jobs, visualization
from app.config import settings
from app.db.database import Base, engine
from app.workers.queue_worker import start_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables (no Alembic for the MVP, per database SKILL).
    Base.metadata.create_all(bind=engine)

    worker_thread = None
    stop_event = None
    if settings.worker_enabled:
        worker_thread, stop_event = start_worker()
        app.state.worker_thread = worker_thread
        app.state.worker_stop_event = stop_event

    try:
        yield
    finally:
        if stop_event is not None:
            stop_event.set()
        if worker_thread is not None:
            worker_thread.join(timeout=5)


app = FastAPI(title="Bagheera API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inference.router)
app.include_router(jobs.router)
app.include_router(annotations.router)
app.include_router(visualization.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
