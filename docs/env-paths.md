# Paths, `.env`, and Docker — where everything lives

This explains how file paths work once Bagheera runs in Docker: what each `.env`
variable means, what you type into it, how it shows up in the **UI file picker**, and
where the same data sits **on the machine itself** (the host) versus **inside the
container**.

> The one rule that explains 90% of path confusion:
>
> **There are two worlds — the *host* (the real machine) and the *container* (inside
> Docker). A "bind mount" is a bridge: it makes one host folder appear at one container
> path. The UI and `TRIDENT_ALLOWED_ROOTS` only ever speak *container* paths. You never
> type a host path like `/media/...` into the UI.**

---

## 1. Host path vs container path

```
   HOST (the machine)                         CONTAINER (inside Docker)
   /media/.../datasets        ──mount──▶      /data           (what the UI sees)
   /media/.../bagheera_state  ──mount──▶      /state/...       (DB, caches, outputs)
```

- A **host path** is where a file really lives on the machine — e.g.
  `/media/multi3090/Expansion/Panther-GUI/datasets`. You see it with `ls` in a normal
  terminal.
- A **container path** is where that same folder appears *inside* Docker — e.g. `/data`.
  The app, the UI picker, and `TRIDENT_ALLOWED_ROOTS` all use container paths.
- The bridge is a line in `docker-compose.yml` like `- ${WSI_DATA_DIR}:/data:ro`, which
  reads: "take the host folder in `WSI_DATA_DIR` and show it at `/data` inside the
  container, read-only (`:ro`)."

**If a container path isn't backed by a mount, anything written there is lost when the
container is rebuilt. If you point an allowed root at a host path the container can't
see, the picker says "Path not found."**

---

## 2. The `.env` variables, grouped

### A. Host-side: *where your data and outputs live on the machine*
These are the **only** variables you set to real machine paths.

| Variable | What you put | Mounted to (container) |
| --- | --- | --- |
| `WSI_DATA_DIR` | Host folder holding **all your slides + the manifest CSV** (can be a parent of many dataset subfolders) | `/data` (read-only) |
| `STATE_DIR_INTERNAL` | Host folder on **fast/local disk** for the DB + model-weight cache | `/state/db`, `/state/hf_cache` |
| `STATE_DIR_EXTERNAL` | Host folder on the **big data disk** for bulk outputs | `/state/viz_cache`, `/state/inference_outputs`, `/app/backend/trident_processed`, `/opt/PANTHER/src/splits/datasets_splits` |

> The stock `.env.example` uses a single `STATE_DIR` for all of the above; this deployment
> splits it into `_INTERNAL` (small/fast) and `_EXTERNAL` (large) — the container paths
> are identical either way.

### B. Container-side: *fixed paths inside Docker — leave these alone*
These are **container** paths. They must match the mount targets above, so don't change
them unless you also change `docker-compose.yml`.

| Variable | Value | Meaning |
| --- | --- | --- |
| `TRIDENT_ALLOWED_ROOTS` | `/data:/app/backend/trident_processed` | The **only** folders the UI picker may browse (colon-separated). `/data` = slides+CSV; `/app/backend/trident_processed` = TRIDENT feature outputs (for the PANTHER form). |
| `BAGHEERA_DB_PATH` | `/state/db/bagheera.db` | SQLite DB file |
| `VIZ_CACHE_ROOT` | `/state/viz_cache` | Heatmaps/UMAPs + job logs |
| `INFERENCE_ROOT` | `/state/inference_outputs` | Per-slide inference outputs |
| `HF_HOME` | `/state/hf_cache` | Downloaded model weights |
| `CUDA_VISIBLE_DEVICES` | `0` | Which GPU the app uses |

### C. Build / misc (not paths)
`CUDA_IMAGE`, `TORCH_INDEX`, `TRIDENT_REF`, `PANTHER_REF`, `FRONTEND_PORT`, `HF_TOKEN`.

---

## 3. The master map: machine ↔ container ↔ UI

This is the table to keep handy. "On the machine" = where you `ls` it in a normal
terminal. "In the container / UI" = the path the app uses.

| What | On the machine (host) | In the container / UI | R/W |
| --- | --- | --- | --- |
| **Slides + manifest CSV** | `$WSI_DATA_DIR/…` | `/data/…` ← *browse here in the UI* | read-only |
| **TRIDENT features (`.h5`)** | `$STATE_DIR_EXTERNAL/trident_processed/…` | `/app/backend/trident_processed/…` ← *browse here for the PANTHER features dir* | read-write |
| **K-fold splits + trained `.pkl`** | `$STATE_DIR_EXTERNAL/datasets_splits/…` | `/opt/PANTHER/src/splits/datasets_splits/…` | read-write |
| **Visualizations (heatmaps, UMAP, top-K)** | `$STATE_DIR_EXTERNAL/viz_cache/<model_id>/…` | `/state/viz_cache/<model_id>/…` | read-write |
| **Job logs** | `$STATE_DIR_EXTERNAL/viz_cache/job_logs/…` | `/state/viz_cache/job_logs/…` | read-write |
| **Inference outputs** | `$STATE_DIR_EXTERNAL/inference_outputs/<model_id>/…` | `/state/inference_outputs/…` | read-write |
| **Database** | `$STATE_DIR_INTERNAL/db/bagheera.db` | `/state/db/bagheera.db` | read-write |
| **Model weights cache** | `$STATE_DIR_INTERNAL/hf_cache/…` | `/state/hf_cache/…` | read-write |

There is one path that is intentionally **not** on the host: the `feats_h5` symlinks under
`/tmp/bagheera/feats_links/…` in the container. They're recreated automatically each run
(your data disk can't hold symlinks), so they don't need to persist.

---

## 4. How this looks in the UI

The file picker dropdown lists exactly the entries in `TRIDENT_ALLOWED_ROOTS` — always
**container** paths:

- **TRIDENT page → WSI directory:** open **`/data`**, drill into the dataset subfolder you
  want, click **Select this folder**. (You select the *folder*; the picker shows only
  subfolders, not the slide files — that's normal.)
- **PANTHER page → Source CSV:** browse **`/data`** → `manifest.csv`.
- **PANTHER page → Features directory:** browse **`/app/backend/trident_processed/<dataset>/20x_…/features_<encoder>`** (or paste it).
- **Inference page → slides:** browse **`/data`**.

If the picker shows **"Path not found,"** an allowed root points at a path the container
can't see — almost always because a **host** path (e.g. `/media/...`) was put into
`TRIDENT_ALLOWED_ROOTS` instead of the **container** path (`/data`). Fix: mount the folder
via `WSI_DATA_DIR` and keep `TRIDENT_ALLOWED_ROOTS=/data:/app/backend/trident_processed`.

---

## 5. "I want to browse a folder-of-datasets and pick one"

Point the mount at the **parent** folder:

```ini
# .env  — host path (the parent that holds all dataset subfolders)
WSI_DATA_DIR=/media/multi3090/Expansion/Panther-GUI/datasets
# container paths only — do NOT put the /media/... host path here
TRIDENT_ALLOWED_ROOTS=/data:/app/backend/trident_processed
```
```bash
docker compose up -d                       # apply the mount
sudo docker compose exec backend ls /data  # should list your dataset subfolders
```
Now in the UI, open **`/data`** and every dataset subfolder is there to pick.

> Folder names with **spaces** or `+` (e.g. `datasets + patients`) work because `/data`
> hides them inside the container, but they can trip up `docker compose` on the host side.
> If `up` complains about the volume, move/symlink the data to a space-free path, or quote
> the value in `.env`.

---

## 6. Seeing your data on the machine (not in the container)

Everything persistent lives under your two state dirs and the WSI dir. To inspect from a
normal terminal (no Docker needed):

```bash
# trained features, splits, models, viz, inference — all on the big disk:
ls "$STATE_DIR_EXTERNAL/trident_processed"
ls "$STATE_DIR_EXTERNAL/datasets_splits"
ls "$STATE_DIR_EXTERNAL/viz_cache"
ls "$STATE_DIR_EXTERNAL/inference_outputs"
# the database + weights on the fast disk:
ls "$STATE_DIR_INTERNAL/db"
ls "$STATE_DIR_INTERNAL/hf_cache"
```

The equivalent *inside* the container (same files, container paths) — useful when a log
prints a `/state/...` or `/app/...` path:

```bash
sudo docker compose exec backend ls /state/viz_cache
sudo docker compose exec backend ls /app/backend/trident_processed
```

Because these are bind mounts, a file the app writes to `/state/viz_cache/...` **is** the
same file at `$STATE_DIR_EXTERNAL/viz_cache/...` on the machine — editing/deleting in one
place affects the other.

---

## 7. Quick rules of thumb

- **Host path** (`/media/...`, `/home/...`) → goes **only** in `WSI_DATA_DIR`,
  `STATE_DIR_INTERNAL`, `STATE_DIR_EXTERNAL`.
- **Container path** (`/data`, `/app/...`, `/state/...`) → everything the **UI** and
  `TRIDENT_ALLOWED_ROOTS` use.
- **Read-only** `/data` — you can't write into the slides mount; the manifest is read from
  there too, so edit the manifest on the **host** (`$WSI_DATA_DIR/manifest.csv`), not in
  the container.
- **Nothing is "stuck in Docker"** — every output is a bind mount onto your disk. The only
  ephemeral path is `/tmp/bagheera/feats_links` (auto-recreated).
- **"Path not found" in the picker** = you used a host path where a container path belongs.
