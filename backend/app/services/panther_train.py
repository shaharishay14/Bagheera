"""Real `panther_train` job handler.

Drives K PANTHER subprocesses sequentially inside the worker thread. Per fold:
inserts a PantherRun row, captures stdout/stderr to the job log, updates the
Model row's status when done. After all K complete, enqueues K
`post_train_viz` jobs (one per fold model).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Job, Model, ModelGroup, PantherRun, Split
from app.services import panther_runner
from app.services.worker import JobLog, enqueue_job, register_handler


class PantherTrainError(RuntimeError):
    pass


def _require_panther_repo() -> str:
    if not settings.panther_repo_path:
        raise PantherTrainError("PANTHER_REPO_PATH is not set on the server.")
    return settings.panther_repo_path


def _train_one_fold(
    *,
    db: Session,
    log: JobLog,
    model: Model,
    split: Split,
    repo_path: str,
) -> str:
    """Run PANTHER for one fold. Returns the Model.status set after the attempt."""
    args = panther_runner.PantherFoldArgs(
        features_dir=model.features_dir,
        split_dir_rel=panther_runner.fold_dir_rel(
            model.dataset_name, split.split_name, model.fold_index
        ),
        mode=model.mode,
        in_dim=model.in_dim,
        n_proto_patches=model.n_proto_patches,
        n_proto=model.n_proto,
        n_init=model.n_init,
        seed=model.seed,
        num_workers=model.num_workers,
    )
    cmd = panther_runner.build_command(args)
    command_str = panther_runner.render_command(cmd)

    run_row = PantherRun(
        id=str(__import__("uuid").uuid4()),
        created_at=datetime.utcnow(),
        group_id=model.group_id,
        fold_index=model.fold_index,
        model_id=model.id,
        dataset_name=model.dataset_name,
        features_dir=model.features_dir,
        split_name=model.split_name,
        mode=model.mode,
        in_dim=model.in_dim,
        n_proto_patches=model.n_proto_patches,
        n_proto=model.n_proto,
        n_init=model.n_init,
        seed=model.seed,
        num_workers=model.num_workers,
        command=command_str,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(run_row)
    db.commit()

    log.write(f"--- fold {model.fold_index + 1}/{model.fold_k} ({model.model_name}) ---")
    log.write(f"$ {command_str}")

    result = panther_runner.execute(
        cmd, cwd=panther_runner.panther_src_dir(repo_path)
    )

    run_row.stdout = result.stdout
    run_row.stderr = result.stderr
    run_row.return_code = result.returncode
    run_row.finished_at = datetime.utcnow()

    if result.returncode == 0:
        prototype_files = panther_runner.scan_prototype_files(Path(model.prototypes_dir))
        if prototype_files:
            model_status = "ready"
        else:
            model_status = "failed"
            log.write(
                f"!! fold {model.fold_index} returned 0 but no .pkl/.pt files under "
                f"{model.prototypes_dir!r}"
            )
    else:
        prototype_files = []
        model_status = "failed"

    model.status = model_status
    model.prototype_files = json.dumps(prototype_files)
    run_row.status = "succeeded" if model_status == "ready" else "failed"
    db.add(model)
    db.add(run_row)
    db.commit()

    log.write(
        f"fold {model.fold_index}: status={model_status} return_code={result.returncode} "
        f"prototype_files={len(prototype_files)}"
    )
    if result.stdout:
        log.write("--- stdout ---")
        log.write(result.stdout.rstrip())
    if result.stderr:
        log.write("--- stderr ---")
        log.write(result.stderr.rstrip())

    panther_runner.between_folds_cleanup()
    return model_status


def handle_panther_train(*, db: Session, job: Job, log: JobLog) -> None:
    repo_path = _require_panther_repo()
    group = db.get(ModelGroup, job.ref_id)
    if group is None:
        raise PantherTrainError(f"ModelGroup {job.ref_id!r} not found.")

    split = db.get(Split, group.split_id)
    if split is None:
        raise PantherTrainError(f"Split {group.split_id!r} referenced by group not found.")

    models = (
        db.query(Model)
        .filter(Model.group_id == group.id)
        .order_by(Model.fold_index.asc())
        .all()
    )
    if not models:
        raise PantherTrainError(f"No models attached to group {group.id!r}.")

    log.write(
        f"Training {len(models)} fold(s) for group {group.id} "
        f"({group.display_name!r}, dataset={group.dataset_name!r}, split={split.split_name!r})"
    )

    succeeded_models: list[Model] = []
    for model in models:
        try:
            status = _train_one_fold(
                db=db, log=log, model=model, split=split, repo_path=repo_path
            )
        except Exception as exc:  # noqa: BLE001
            log.write(f"!! fold {model.fold_index} raised: {exc}")
            model.status = "failed"
            db.add(model)
            db.commit()
            status = "failed"
        if status == "ready":
            succeeded_models.append(model)

    log.write(
        f"Training done. {len(succeeded_models)}/{len(models)} folds ready. "
        f"Enqueuing post_train_viz jobs."
    )
    for model in succeeded_models:
        enqueue_job(db, job_type="post_train_viz", ref_table="models", ref_id=model.id)


def register() -> None:
    register_handler("panther_train", handle_panther_train)
