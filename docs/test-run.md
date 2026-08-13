# ☆ DEAD-SIMPLE QUICKSTART (read this first)

You do **not** start the backend and frontend separately. Docker runs both for you.
You type a few commands once, then do **everything else in the web browser**.

### Step 1 — put your files on the GPU machine
Make a folder with your 5 slides and one CSV inside it:
```
/home/you/wsi_data/
├── slideA.svs
├── slideB.svs
├── slideC.svs
├── slideD.svs
├── slideE.svs
└── manifest.csv
```
`manifest.csv` is just a list of the slide names **without the file extension**:
```csv
slide_id
slideA
slideB
slideC
slideD
slideE
```

### Step 2 — tell Docker where things are (once)
```bash
cd Bagheera
cp .env.example .env
nano .env
```
Set just these two lines (leave everything else as-is):
```
WSI_DATA_DIR=/home/you/wsi_data
STATE_DIR=/home/you/bagheera_state
```
`STATE_DIR` is an empty folder Docker fills with results — you don't create anything in it.

### Step 3 — start everything (one command)
```bash
docker compose build      # first time only, slow (downloads + installs)
docker compose up -d      # starts BOTH the backend and the frontend
```
That's it — backend and frontend are now both running.

### Step 4 — open the app
In the browser **on the GPU machine**, go to:
```
http://localhost:8080
```
Now you do the whole pipeline by clicking through the pages — nothing else in the terminal.

### What about the database?
**Nothing to do.** The SQLite database (`bagheera.db`) creates itself automatically the
first time the backend starts — every table is built on boot (`create_all()`), and the file
lives at `$STATE_DIR/db/bagheera.db`. You never run a "create database" or "migrate" command.

### How do I see it's working / watch progress?
```bash
docker compose logs -f backend      # live backend log; Ctrl-C to stop watching
```

### How do I stop / restart?
```bash
docker compose down                 # stop (your results in STATE_DIR are kept)
docker compose up -d                # start again
```

### Then what? — do these 3 things in the browser (details in §5 below)
1. **TRIDENT** page → point at `/data`, pick encoder `phikon`, run. Wait for it to finish.
2. **PANTHER** page → make a split from `/data/manifest.csv` with **k = 3**, then start training
   (set **in_dim = 768** for phikon).
3. **Models** page → watch the folds turn green and the pictures appear.

> ⚠️ Two settings that *must* be right or it fails: split **k = 3** (not 2), and
> **in_dim = 768** when the encoder is phikon. Why → see §5.

---

# First end-to-end test run (5 WSIs → TRIDENT → PANTHER)

A smoke test that exercises the whole pipeline on real hardware with a tiny dataset.
Goal: prove the `.sh` wrappers run, the GPU is visible, paths line up, TRIDENT writes
`.h5` features, PANTHER writes `.pkl` prototypes, and the viz renders.

> The renderers + inference plumbing were written without a GPU (see
> [structure.md §9](./structure.md)). Treat each checkpoint below as a thing to verify,
> not assume.

---

## 0. The mental model (what feeds what)

```
5 WSIs in a folder ─┐
                    ├─► TRIDENT (uses the FOLDER, not the CSV) ─► features dir of .h5
manifest.csv  ──────┘                                                    │
   (slide_id per slide)                                                  │
        │                                                                ▼
        └─► K-fold SPLIT (train/val/test.csv per fold) ────► PANTHER train ─► .pkl prototypes
                                                                         │
                                                                         ▼
                                                                  per-fold viz
```

- **TRIDENT input = the directory.** It tiles + encodes *every* slide in `--wsi_dir`. The
  CSV is irrelevant here.
- **The CSV is the split manifest.** Its `slide_id` values must match the WSI filename
  **stems** (`TCGA-AA-1234.svs` → `TCGA-AA-1234`), because PANTHER looks up each slide's
  `.h5` by that stem in the features dir.

---

## 1. How to run after editing docker-compose.yml

- Changed only a **host path in `.env`** (`WSI_DATA_DIR`, `STATE_DIR`) or a **volume mount
  target** in `docker-compose.yml` → no rebuild needed:
  ```bash
  docker compose up -d        # recreates containers with the new mounts
  ```
- Changed the **Dockerfile, backend code, or `TRIDENT_REF`/`PANTHER_REF`** → rebuild:
  ```bash
  docker compose build && docker compose up -d
  ```
- Watch the backend the whole time:
  ```bash
  docker compose logs -f backend
  ```

---

## 2. Lay out the test data on the host

```
$WSI_DATA_DIR/                 # this becomes /data:ro in the container
├── slideA.svs
├── slideB.svs
├── slideC.svs
├── slideD.svs
├── slideE.svs
└── manifest.csv               # the split manifest
```

`manifest.csv` — header + one row per slide. The first column must be the slide id
(stem). `slide_id` is the detected column; `case_id`/`label` are optional and just carried
through:

```csv
slide_id,case_id,label
slideA,slideA,0
slideB,slideB,0
slideC,slideC,1
slideD,slideD,1
slideE,slideE,0
```

Put `manifest.csv` **inside `$WSI_DATA_DIR`** so it lands under `/data` and passes the path
sandbox (`TRIDENT_ALLOWED_ROOTS=/data`). The split step browses to it as
`/data/manifest.csv`.

---

## 3. `.env` settings that matter for the test

| Key | Use for the test |
| --- | --- |
| `WSI_DATA_DIR` | host folder with the 5 slides + manifest |
| `STATE_DIR` | host folder for DB/outputs (will fill with `trident_processed/`, `viz_cache/`, …) |
| `CUDA_IMAGE` / `TORCH_INDEX` | match `nvidia-smi` (12.1 default, else cu118 — see docs/docker.md) |
| `TRIDENT_ALLOWED_ROOTS` | `/data` |
| `CUDA_VISIBLE_DEVICES` | `0` |
| `HF_TOKEN` | **leave blank** — use the non-gated `phikon` encoder so no token is needed |

---

## 4. Pre-flight smoke tests (before touching the UI)

```bash
# GPU visible to torch inside the container
docker compose run --rm backend /opt/venv/bin/python -c "import torch; print(torch.cuda.is_available())"   # True
# openslide can open one of your slides
docker compose run --rm backend /opt/venv/bin/python -c "import openslide; print(openslide.open_slide('/data/slideA.svs').dimensions)"
# API + the path sandbox
curl http://localhost:8080/api/fs/roots          # → ["/data"]
curl "http://localhost:8080/api/fs/list?path=/data"   # lists your 5 slides + manifest.csv
```

If any fail, stop and fix here — the pipeline can't pass these.

---

## 5. The run, step by step (do it through the UI at http://localhost:8080)

### Step A — TRIDENT extraction  (`/training/trident`)
1. WSI dir → `/data`; dataset name → e.g. `testrun` (must match `^[A-Za-z0-9_-]+$`);
   encoder → **`phikon`** (patch size 224, in_dim 768, not gated).
2. Submit. **This blocks** (sync run) — watch `docker compose logs -f backend`.
3. ✅ **Checkpoint:** 5 `.h5` files appear at
   ```
   $STATE_DIR/trident_processed/testrun/20x_224px_0px_overlap/features_phikon/*.h5
   ```
   (in-container: `/app/backend/trident_processed/...`). One `.h5` per slide, stems
   matching your `slide_id`s.

### Step B — Create the split  (`/training/panther`, split section)
1. Point at the features dir from Step A (the server resolves it back to the TridentRun).
2. Create a new split: source CSV → `/data/manifest.csv`; **k → `3`**; seed → `1`.
3. ✅ **Checkpoint:** split created with non-empty train counts. Verify on disk
   (note: splits are written into the PANTHER repo dir, see §7):
   ```
   docker compose exec backend ls /opt/PANTHER/src/datasets_splits/testrun/*/k=0/
   # → train.csv val.csv test.csv ; train.csv must have >0 data rows
   ```

> ⚠️ **Use k ≥ 3.** With k=2 the splitter produces an **empty train set** (train = the
> K−2 = 0 chunks not used for test/val), and PANTHER will fail. k=3 over 5 slides gives
> train sizes of 1–2 — tiny but enough to smoke-test.

### Step C — PANTHER training  (`/training/panther`, train section)
1. Model name → e.g. `testrun_panther`. Pick the split from Step B.
2. Hyperparameters — **set `in_dim` to match the encoder**:
   - `phikon` / `phikon_v2` → **`in_dim = 768`**  ← the form defaults to 1024 (uni); change it.
   - `uni_v1` → 1024, `uni_v2` → 1536.
   - Leave `mode=faiss`, `n_proto=16`, `n_init=5`. Consider lowering `n_proto_patches`
     (default 1,000,000) — with 5 tiny slides there are far fewer patches, but it's a cap,
     so the default is safe.
3. Submit → returns immediately, navigates to the group detail page; **one `panther_train`
   job** is enqueued and the worker runs the K folds sequentially.
4. Watch the job log:
   ```bash
   ls -t $STATE_DIR/viz_cache/job_logs/ | head    # newest job log
   tail -f $STATE_DIR/viz_cache/job_logs/<job_id>.log
   ```
5. ✅ **Checkpoint:** each fold ends `status=ready return_code=0` with `prototype_files>0`.
   A returncode 0 but **no `.pkl`** is reported as `failed` — that means PANTHER ran but
   wrote prototypes somewhere other than where `scan_prototype_files` looks.

### Step D — Post-train viz (automatic)
Each ready fold auto-enqueues a `post_train_viz` job (heatmaps + top-K grid + UMAP).
6. ✅ **Checkpoint:** `$STATE_DIR/viz_cache/<model_id>/` fills with PNGs and the group
   detail page shows real images instead of SVG placeholders.

### Step E — (optional) Inference on a held-out slide  (`/models/:modelId/inference`)
Run a ready fold model against one of the slides → TRIDENT re-extracts that slide async,
then renders heatmap/mixture/example-patches/t-SNE. ✅ Per-slide PNGs under
`$STATE_DIR/inference_outputs/<model_id>/<inference_id>/`.

---

## 6. Where to look when a step fails

| Symptom | Likely cause |
| --- | --- |
| `could not select device driver "nvidia"` | NVIDIA Container Toolkit not installed / Docker not restarted (docs/docker.md §1). |
| `/api/fs/roots` not `["/data"]`, browser empty | `TRIDENT_ALLOWED_ROOTS` must be the **container** path `/data`, not a host path. |
| TRIDENT: no `.h5` written | encoder/slide-format issue; read the run's stdout/stderr in the UI or backend logs. |
| Split: empty `train.csv` | used k=2 — use k ≥ 3. |
| PANTHER: returncode 0 but `failed` | prototypes written outside `model.prototypes_dir`; check the fold's stdout for the real output path. |
| PANTHER: shape/dim error | `in_dim` doesn't match the encoder's feature dim (phikon=768). |
| Viz: placeholders persist | `post_train_viz` job failed — check its job log; usually a PANTHER `.pkl` structure assumption (see visualization.py docstring). |

Every async failure is captured: job row → `status=failed` + `error_message`, full
traceback in the job log. The worker never dies, so the queue keeps moving.

---

## 7. Path wiring notes (verified against the code)

These are internally consistent for a single test run, but worth knowing:

- **TRIDENT output** → `/app/backend/trident_processed/...`, mounted to
  `$STATE_DIR/trident_processed`. ✅ Persisted.
- **Splits** → the splits route **prefers `$PANTHER_REPO_PATH/src/datasets_splits`**
  (`routes/splits.py:_output_root_for`) whenever `PANTHER_REPO_PATH` is set — which it
  always is in the image (`/opt/PANTHER`). PANTHER reads from the *same* place (cwd-relative
  `datasets_splits/...` under `/opt/PANTHER/src`), so **training finds the split**. ✅ for
  the test.
  - ⚠️ But this means `DATASETS_SPLITS_ROOT=/state/datasets_splits` and its volume mount are
    effectively **unused**, and splits live in the container's writable layer — they're
    **lost when the container is recreated** (`docker compose down`/rebuild). Fine for a
    one-shot test; if you want splits to persist, mount the state volume *over* the repo
    path instead: `- ${STATE_DIR}/datasets_splits:/opt/PANTHER/src/datasets_splits`.
- **Features dir passed to PANTHER** (`--data_source`) is the absolute TRIDENT output dir,
  so PANTHER reads `.h5` straight from the persisted `trident_processed` volume. ✅
