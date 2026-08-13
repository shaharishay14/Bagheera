"""Demo data seeder for the Bagheera Models/Group detail pages.

Populates the DB with a representative scenario matrix so the UI can be
exercised without running real TRIDENT/PANTHER subprocesses.

Usage (run from anywhere; chdirs to the backend dir internally):
    python backend/scripts/seed_demo.py          # idempotent: wipe [SEED] rows + recreate
    python backend/scripts/seed_demo.py --reset  # wipe [SEED] rows only

Seed marker
-----------
Every row touched by this script carries a `[SEED]` prefix on a recognizable
column so it can never be confused with real data:
  - ModelGroup.display_name, Model.display_name : "[SEED] ..."
  - TridentRun.dataset_name, Split.dataset_name, Model.dataset_name : "[SEED]demo_*"
  - Split.split_name                                                 : "[SEED]kfold_..."

The wipe step uses these prefixes to identify and remove seed-only rows;
real training data is left untouched.

Path columns
------------
For viz_status='ready' models, the per-fold path columns are populated with
placeholder-endpoint URLs of the form:
    /api/viz/placeholder/{kind}?label=...&model_id={id}&...
The `model_id=` discriminator makes it obvious in the DB that a path was
written by the seeder; PR 3's real renderer should overwrite these with
real `/api/viz/{file}` paths when it produces actual images.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Make sure we can import `app.*` and that bagheera.db resolves to the backend dir.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import (  # noqa: E402
    Inference,
    InferenceBatch,
    InferenceNote,
    Job,
    Model,
    ModelGroup,
    ModelNote,
    PantherRun,
    PrototypeLabel,
    Split,
    TridentRun,
)

SEED_PREFIX = "[SEED]"
DATASET_A = f"{SEED_PREFIX}demo_brca"
DATASET_B = f"{SEED_PREFIX}demo_lung"

# Deterministic UUID namespace so repeat runs produce stable IDs.
NAMESPACE = uuid.UUID("c1a5e1d0-5eed-4eed-9eed-5eed5eed5eed")


def sid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"bagheera-seed:{name}"))


def _slug(s: str) -> str:
    """Compact, model_name-safe slug derived from a display string."""
    cleaned = s.replace(SEED_PREFIX, "").strip().lower()
    return re.sub(r"[^a-z0-9_-]+", "_", cleaned).strip("_") or "seed"


# ---------------------------------------------------------------------------
# Wipe
# ---------------------------------------------------------------------------


def wipe_seed_data(db) -> dict[str, int]:
    """Delete every row this script could have created. Returns a counts dict."""
    counts: dict[str, int] = {}

    # Identify seed groups + models first; we use their ids to scope downstream deletes
    # so we don't accidentally torch real data that happens to share a name.
    seed_groups = (
        db.query(ModelGroup).filter(ModelGroup.display_name.like(f"{SEED_PREFIX}%")).all()
    )
    group_ids = [g.id for g in seed_groups]

    seed_models = (
        db.query(Model).filter(Model.group_id.in_(group_ids)).all() if group_ids else []
    )
    model_ids = [m.id for m in seed_models]

    if model_ids:
        # Children of models
        counts["prototype_labels"] = (
            db.query(PrototypeLabel)
            .filter(PrototypeLabel.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        counts["model_notes"] = (
            db.query(ModelNote)
            .filter(ModelNote.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        # Inferences + their notes (in case a future seed creates them)
        seed_inference_ids = [
            row.id
            for row in db.query(Inference.id).filter(Inference.model_id.in_(model_ids)).all()
        ]
        if seed_inference_ids:
            counts["inference_notes"] = (
                db.query(InferenceNote)
                .filter(InferenceNote.inference_id.in_(seed_inference_ids))
                .delete(synchronize_session=False)
            )
        counts["inferences"] = (
            db.query(Inference)
            .filter(Inference.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        counts["inference_batches"] = (
            db.query(InferenceBatch)
            .filter(InferenceBatch.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        counts["panther_runs"] = (
            db.query(PantherRun)
            .filter(PantherRun.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        # Jobs that reference these models
        counts["jobs_models"] = (
            db.query(Job)
            .filter(Job.ref_table == "models", Job.ref_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        counts["models"] = (
            db.query(Model)
            .filter(Model.id.in_(model_ids))
            .delete(synchronize_session=False)
        )

    if group_ids:
        counts["jobs_groups"] = (
            db.query(Job)
            .filter(Job.ref_table == "model_groups", Job.ref_id.in_(group_ids))
            .delete(synchronize_session=False)
        )
        counts["model_groups"] = (
            db.query(ModelGroup)
            .filter(ModelGroup.id.in_(group_ids))
            .delete(synchronize_session=False)
        )

    counts["splits"] = (
        db.query(Split)
        .filter(Split.split_name.like(f"{SEED_PREFIX}%"))
        .delete(synchronize_session=False)
    )
    counts["trident_runs"] = (
        db.query(TridentRun)
        .filter(TridentRun.dataset_name.like(f"{SEED_PREFIX}%"))
        .delete(synchronize_session=False)
    )

    db.commit()
    return counts


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------


def _viz_url(kind: str, model_id: str, *, label: str, width: int, height: int, **extra: object) -> str:
    """Placeholder-endpoint URL stored in a path column.

    The `model_id=` query param is the discriminator that distinguishes a
    seed-written path from a real one PR 3 will write.
    """
    parts = [
        f"label={label.replace(' ', '+')}",
        f"width={width}",
        f"height={height}",
        f"model_id={model_id}",
    ]
    for k, v in extra.items():
        parts.append(f"{k}={v}")
    return f"/api/viz/placeholder/{kind}?{'&'.join(parts)}"


def seed_trident_run(db, dataset_name: str, encoder: str = "uni_v1") -> TridentRun:
    run_id = sid(f"trident:{dataset_name}")
    run = TridentRun(
        id=run_id,
        created_at=datetime.utcnow() - timedelta(days=7),
        dataset_name=dataset_name,
        wsi_dir=f"/seed/wsis/{_slug(dataset_name)}",
        patch_encoder=encoder,
        mag=20,
        patch_size=256,
        command="(seed)",
        status="succeeded",
        output_dir=f"/seed/features/{_slug(dataset_name)}/20x_256px_0px_overlap/features_{encoder}",
        stdout="",
        stderr="",
        return_code=0,
    )
    db.add(run)
    return run


def seed_split(db, dataset_name: str, k: int, seed_val: int = 42) -> Split:
    split_id = sid(f"split:{dataset_name}:k{k}:s{seed_val}")
    split_name = f"{SEED_PREFIX}kfold_k_{k}_seed_{seed_val}_{_slug(dataset_name)}"
    per_fold = [{"train": 80, "val": 10, "test": 10}] * k
    split = Split(
        id=split_id,
        created_at=datetime.utcnow() - timedelta(days=6),
        dataset_name=dataset_name,
        split_name=split_name,
        abs_path=f"/seed/splits/{_slug(dataset_name)}/{split_name}",
        source_csv=f"/seed/manifests/{_slug(dataset_name)}.csv",
        k=k,
        seed=seed_val,
        total_rows=100,
        per_fold_counts=json.dumps(per_fold),
    )
    db.add(split)
    return split


def seed_group(
    db,
    *,
    display_name: str,
    name_slug: str,
    dataset_name: str,
    trident_run: TridentRun,
    split: Split,
    k: int,
    fold_statuses: list[str],
    viz_statuses: list[str],
    favorited_indexes: tuple[int, ...] = (),
    labels: list[str] | None = None,
    note_body: str | None = None,
    n_proto: int = 16,
    mode: str = "faiss",
) -> tuple[ModelGroup, list[Model]]:
    assert len(fold_statuses) == k and len(viz_statuses) == k, "patterns must match K"
    group_id = sid(f"group:{display_name}")
    group = ModelGroup(
        id=group_id,
        created_at=datetime.utcnow() - timedelta(days=3),
        display_name=display_name,
        dataset_name=dataset_name,
        trident_run_id=trident_run.id,
        k=k,
        split_id=split.id,
    )
    db.add(group)

    models: list[Model] = []
    for i in range(k):
        model_id = sid(f"model:{display_name}:k{i}")
        status = fold_statuses[i]
        viz_status = viz_statuses[i]

        preview_slide_ids: list[str] | None = None
        preview_heatmap_paths: list[str] | None = None
        topk_grid_path: str | None = None
        umap_path: str | None = None

        if viz_status == "ready":
            preview_slide_ids = [f"{_slug(dataset_name)}_slide_{i:02d}_{j:02d}" for j in range(3)]
            preview_heatmap_paths = [
                _viz_url(
                    "heatmap",
                    model_id,
                    label=f"Slide+{j + 1}+(fold+{i + 1})",
                    width=360,
                    height=240,
                    slide=j,
                )
                for j in range(3)
            ]
            topk_grid_path = _viz_url(
                "topk",
                model_id,
                label=f"{n_proto}+prototypes+x+3",
                width=720,
                height=320,
            )
            umap_path = _viz_url(
                "umap",
                model_id,
                label=f"UMAP+(fold+{i + 1})",
                width=720,
                height=320,
            )

        model = Model(
            id=model_id,
            created_at=datetime.utcnow() - timedelta(days=2, hours=i),
            base_name=name_slug,
            model_name=f"{name_slug}_k{i}",
            display_name=display_name,
            group_id=group_id,
            fold_index=i,
            fold_k=k,
            dataset_name=dataset_name,
            features_dir=trident_run.output_dir,
            trident_run_id=trident_run.id,
            split_id=split.id,
            split_name=split.split_name,
            split_dir_abs=f"{split.abs_path}/k={i}",
            mode=mode,
            in_dim=1024,
            n_proto_patches=1_000_000,
            n_proto=n_proto,
            n_init=5,
            seed=1,
            num_workers=10,
            status=status,
            prototypes_dir=f"{split.abs_path}/k={i}/prototypes",
            prototype_files=json.dumps(["prototypes_c16.pkl"]) if status == "ready" else "[]",
            is_favorite=(i in favorited_indexes),
            viz_status=viz_status,
            preview_slide_ids=json.dumps(preview_slide_ids) if preview_slide_ids else None,
            preview_heatmap_paths=(
                json.dumps(preview_heatmap_paths) if preview_heatmap_paths else None
            ),
            topk_grid_path=topk_grid_path,
            topk_per_proto=3,
            umap_path=umap_path,
        )
        db.add(model)
        models.append(model)

    db.commit()  # flush so labels/notes can reference model ids

    if labels:
        target = models[0]
        now = datetime.utcnow()
        for idx, label in enumerate(labels[: target.n_proto]):
            db.add(
                PrototypeLabel(
                    id=sid(f"label:{target.id}:{idx}"),
                    created_at=now,
                    updated_at=now,
                    model_id=target.id,
                    prototype_index=idx,
                    label=label,
                )
            )

    if note_body:
        target = models[0]
        when = datetime.utcnow() - timedelta(hours=2)
        db.add(
            ModelNote(
                id=sid(f"note:{target.id}:0"),
                created_at=when,
                updated_at=when,
                model_id=target.id,
                body=note_body,
            )
        )

    db.commit()
    return group, models


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------


def seed_inferences_for_brca_v1(db, group: ModelGroup) -> int:
    """Three demo inferences against fold 0 of the BRCA v1 group:
    two ready (different slides), one failed. All under one batch.

    All paths point under /seed/wsis/... — the files don't need to exist
    on disk; the seed sets viz paths to the placeholder endpoint so the
    UI renders something even without real files.
    """
    fold_zero = (
        db.query(Model)
        .filter(Model.group_id == group.id, Model.fold_index == 0)
        .one_or_none()
    )
    if fold_zero is None:
        return 0

    batch_id = sid(f"inf_batch:{group.id}")
    db.add(
        InferenceBatch(
            id=batch_id,
            created_at=datetime.utcnow() - timedelta(hours=4),
            model_id=fold_zero.id,
            user_label=f"{SEED_PREFIX} pilot batch",
            total_count=3,
        )
    )

    specs = [
        {
            "label": "ready_slide_a",
            "status": "ready",
            "filename": "seed_brca_ready_a.svs",
            "size": 4_500_000_000,
            "error": None,
        },
        {
            "label": "ready_slide_b",
            "status": "ready",
            "filename": "seed_brca_ready_b.svs",
            "size": 5_200_000_000,
            "error": None,
        },
        {
            "label": "failed_slide",
            "status": "failed",
            "filename": "seed_brca_failed.svs",
            "size": 3_800_000_000,
            "error": "TRIDENT exited with code 1: openslide failed to read level 0",
        },
    ]

    for spec in specs:
        inf_id = sid(f"inference:{group.id}:{spec['label']}")
        wsi_path = f"/seed/wsis/demo_brca/{spec['filename']}"
        is_ready = spec["status"] == "ready"

        viz_paths = {}
        if is_ready:
            viz_paths = {
                "heatmap_path": _viz_url(
                    "heatmap",
                    inf_id,
                    label=spec["filename"].replace(".svs", "").replace("_", "+"),
                    width=800,
                    height=500,
                ),
                "mixture_plot_path": _viz_url(
                    "mixture", inf_id, label="Mixture", width=600, height=300
                ),
                "example_patches_dir": f"/seed/viz/{inf_id}/example_patches",
                "tsne_path": _viz_url(
                    "tsne", inf_id, label="t-SNE", width=600, height=500
                ),
            }
        else:
            viz_paths = {
                "heatmap_path": None,
                "mixture_plot_path": None,
                "example_patches_dir": None,
                "tsne_path": None,
            }

        db.add(
            Inference(
                id=inf_id,
                created_at=datetime.utcnow() - timedelta(hours=3),
                finished_at=datetime.utcnow() - timedelta(hours=2) if is_ready or spec["error"] else None,
                model_id=fold_zero.id,
                batch_id=batch_id,
                wsi_path=wsi_path,
                wsi_filename=spec["filename"],
                wsi_mtime=1_700_000_000.0,
                wsi_size=spec["size"],
                wsi_hash="seed" + inf_id.replace("-", "")[:60],
                output_dir=f"/seed/inference_outputs/{fold_zero.id}/{inf_id}",
                features_h5_path=(
                    f"/seed/inference_outputs/{fold_zero.id}/{inf_id}"
                    f"/trident_output/20x_256px_0px_overlap/features_uni_v1/"
                    f"{spec['filename'].replace('.svs', '')}.h5"
                    if is_ready
                    else None
                ),
                status=spec["status"],
                error_message=spec["error"],
                **viz_paths,
            )
        )

        if is_ready:
            note_id = sid(f"inference_note:{inf_id}")
            db.add(
                InferenceNote(
                    id=note_id,
                    created_at=datetime.utcnow() - timedelta(hours=1),
                    updated_at=datetime.utcnow() - timedelta(hours=1),
                    inference_id=inf_id,
                    body=(
                        "Strong prototype 4 (necrosis) signal in the upper-left "
                        "quadrant. Worth re-running with higher mag if storage allows."
                    ),
                )
            )

    db.commit()
    return len(specs)


def seed_all(db) -> list[ModelGroup]:
    tr_a = seed_trident_run(db, DATASET_A)
    tr_b = seed_trident_run(db, DATASET_B)
    db.commit()

    split_a_k5 = seed_split(db, DATASET_A, k=5, seed_val=42)
    split_a_k5_v2 = seed_split(db, DATASET_A, k=5, seed_val=43)
    split_b_k3 = seed_split(db, DATASET_B, k=3, seed_val=42)
    split_b_k10 = seed_split(db, DATASET_B, k=10, seed_val=42)
    db.commit()

    groups: list[ModelGroup] = []

    g1, _ = seed_group(
        db,
        display_name=f"{SEED_PREFIX} BRCA Pilot v1",
        name_slug="seed_brca_v1",
        dataset_name=DATASET_A,
        trident_run=tr_a,
        split=split_a_k5,
        k=5,
        fold_statuses=["ready"] * 5,
        viz_statuses=["ready"] * 5,
        favorited_indexes=(1, 3),
        labels=["necrosis", "epithelium", "fat", "lymphocytes", "stroma"],
        note_body=(
            "**Pilot run.** Looks promising on fold 1 — prototypes align well "
            "with the necrosis/epithelium split visible in the heatmaps. "
            "Need to discuss fold 3 result with team."
        ),
        n_proto=16,
    )
    groups.append(g1)

    g2, _ = seed_group(
        db,
        display_name=f"{SEED_PREFIX} BRCA Pilot v2 (mixed)",
        name_slug="seed_brca_v2_mixed",
        dataset_name=DATASET_A,
        trident_run=tr_a,
        split=split_a_k5_v2,
        k=5,
        fold_statuses=["ready", "ready", "failed", "ready", "ready"],
        viz_statuses=["ready", "ready", "failed", "ready", "ready"],
        n_proto=16,
    )
    groups.append(g2)

    g3, _ = seed_group(
        db,
        display_name=f"{SEED_PREFIX} Lung Triage K=3 (rendering)",
        name_slug="seed_lung_k3_rendering",
        dataset_name=DATASET_B,
        trident_run=tr_b,
        split=split_b_k3,
        k=3,
        fold_statuses=["ready"] * 3,
        viz_statuses=["rendering"] * 3,
        n_proto=8,
    )
    groups.append(g3)

    g4, _ = seed_group(
        db,
        display_name=f"{SEED_PREFIX} Lung Triage K=10",
        name_slug="seed_lung_k10",
        dataset_name=DATASET_B,
        trident_run=tr_b,
        split=split_b_k10,
        k=10,
        fold_statuses=["ready"] * 10,
        viz_statuses=["ready"] * 10,
        favorited_indexes=(2,),
        n_proto=12,
    )
    groups.append(g4)

    # PR 5 demo: a small inference batch under BRCA Pilot v1 fold 0.
    seed_inferences_for_brca_v1(db, g1)

    return groups


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo data into the Bagheera DB.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe [SEED] rows without re-creating them.",
    )
    args = parser.parse_args()

    init_db()  # safe no-op if schema already exists

    db = SessionLocal()
    try:
        print(f"Backend dir: {BACKEND_ROOT}")
        print("Wiping existing [SEED] rows…")
        wiped = wipe_seed_data(db)
        if wiped:
            for table, n in wiped.items():
                if n:
                    print(f"  - {table}: {n}")
        else:
            print("  (nothing to wipe)")

        if args.reset:
            print("Reset only — done.")
            return 0

        print("Seeding scenario matrix…")
        groups = seed_all(db)
        print(f"Inserted {len(groups)} model groups:")
        for g in groups:
            ms = db.query(Model).filter(Model.group_id == g.id).all()
            statuses = ", ".join(sorted({m.status for m in ms}))
            viz = ", ".join(sorted({m.viz_status for m in ms}))
            favs = sum(1 for m in ms if m.is_favorite)
            print(
                f"  - {g.display_name}\n"
                f"      dataset={g.dataset_name}  K={g.k}  models={len(ms)}\n"
                f"      status={{{statuses}}}  viz={{{viz}}}  favorited={favs}"
            )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
