"""FastAPI entrypoint for the Bagheera backend."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import ensure_storage_dirs, settings
from app.db.database import init_db
from app.routes import (
    fs,
    inference,
    jobs,
    labels,
    models,
    notes,
    panther,
    queue,
    runs,
    splits,
    trident,
    viz,
)
from app.services import inference_job, panther_train, post_train_viz, worker
from app.services.job_handlers import register_stub_handlers


def _register_handlers() -> None:
    # Stubs first (registers all three), then real handlers overwrite the slots
    # they own. As more real handlers land, register them here.
    register_stub_handlers()
    panther_train.register()
    post_train_viz.register()
    inference_job.register()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_storage_dirs()
    _register_handlers()
    worker.start_worker()
    try:
        yield
    finally:
        worker.stop_worker()


app = FastAPI(title="Bagheera", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fs.router)
app.include_router(trident.router)
app.include_router(panther.router)
app.include_router(runs.router)
app.include_router(splits.router)
app.include_router(models.router)
app.include_router(labels.router)
app.include_router(notes.router)
app.include_router(inference.router)
app.include_router(jobs.router)
app.include_router(queue.router)
app.include_router(viz.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
