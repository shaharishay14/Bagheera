# Docker + GPU deployment

Run Bagheera (backend + frontend) on a single GPU machine via `git clone` +
`docker compose up`. Everything runs on **localhost** — no domain, no TLS, no CORS.

```
browser (on the GPU box, via AnyDesk)
   → :8080  frontend container (nginx: serves SPA, proxies /api/* → backend)
   → :8000  backend container (FastAPI + worker + baked-in TRIDENT/PANTHER, GPU)
                 │
            mounted volumes:  /data (WSI, ro)   /state/* (DB, caches, outputs, HF weights)
```

The **backend container is the GPU container**: the worker thread lazily imports
torch/openslide/etc. and shells out to the TRIDENT and PANTHER repos baked into the
image. The frontend container is just nginx.

---

## 1. Host prerequisites (once, on the GPU machine)

1. **Docker Engine + Compose v2.**
2. **NVIDIA driver** — verify: `nvidia-smi` prints your GPU.
3. **NVIDIA Container Toolkit** — lets containers see the GPU:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```
4. **Smoke-test GPU passthrough:**
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
   ```
   If this prints the GPU table, the toolkit works.

### Pick the CUDA tag

Run `nvidia-smi` and read **"CUDA Version: XX.X"** (top-right) — that's the *max* CUDA the
driver supports. Choose a base image ≤ that:

| Driver reports | `CUDA_IMAGE` | `TORCH_INDEX` |
| --- | --- | --- |
| 12.1+ | `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` (default) | `https://download.pytorch.org/whl/cu121` |
| 11.8–12.0 | `nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04` | `https://download.pytorch.org/whl/cu118` |

Set both in `.env`.

---

## 2. Configure

```bash
git clone <bagheera-repo> && cd Bagheera
git checkout docker-setup
cp .env.example .env
# edit .env — see the table below
```

| `.env` key | What to set |
| --- | --- |
| `WSI_DATA_DIR` | Host dir holding your slides (mounted read-only at `/data`) |
| `STATE_DIR` | Host dir for persistent state (DB, caches, outputs, HF weights) |
| `CUDA_IMAGE` / `TORCH_INDEX` | Match the driver (table above) |
| `TRIDENT_REF` / `PANTHER_REF` | Git branch/tag to pin each repo |
| `HF_TOKEN` | HuggingFace token — only if you use a **gated** encoder (e.g. `uni`) |
| `TRIDENT_ALLOWED_ROOTS` | Container paths the UI may browse; default `/data` |

The `*_ROOT` / `BAGHEERA_DB_PATH` values are **container paths** — leave them unless you
also change the volume mounts in `docker-compose.yml`.

---

## 3. Build & run

```bash
docker compose build      # installs torch + TRIDENT + PANTHER into one venv (slow first time)
docker compose up -d
# open http://localhost:8080   (or http://<LAN-IP>:8080 from another machine)
docker compose logs -f backend
```

Stop / update:
```bash
docker compose down                       # stops containers; volumes (state) persist
docker compose build && docker compose up -d   # rebuild after a code or repo-ref change
```

---

## 4. Volume layout

Under your `STATE_DIR` on the host:

| Host path | Container path | Holds |
| --- | --- | --- |
| `$STATE_DIR/db` | `/state/db` | `bagheera.db` (SQLite) |
| `$STATE_DIR/viz_cache` | `/state/viz_cache` | heatmaps, UMAPs, **job logs** (`job_logs/`) |
| `$STATE_DIR/inference_outputs` | `/state/inference_outputs` | per-inference TRIDENT features + viz |
| `$STATE_DIR/datasets_splits` | `/state/datasets_splits` | K-fold split folders |
| `$STATE_DIR/trident_processed` | `/app/backend/trident_processed` | initial-dataset TRIDENT outputs |
| `$STATE_DIR/hf_cache` | `/state/hf_cache` | downloaded model weights (`HF_HOME`) |
| `$WSI_DATA_DIR` | `/data` (ro) | your WSI slides |

`viz_cache` and `inference_outputs` grow unbounded — prune manually as needed.

---

## 5. Verify (end-to-end)

```bash
# torch sees the GPU inside the container
docker compose run --rm backend /opt/venv/bin/python -c "import torch; print(torch.cuda.is_available())"   # True
# openslide loads
docker compose run --rm backend /opt/venv/bin/python -c "import openslide; print(openslide.__version__)"
# API reachable through nginx
curl http://localhost:8080/api/fs/roots     # → ["/data"]
```

Then in the browser: load the UI, browse `/data`, kick off a small TRIDENT extraction, and
watch `\$STATE_DIR/viz_cache/job_logs/` for GPU activity and a written `.h5`.

---

## 6. Gotchas / troubleshooting

- **`docker compose build` fails resolving Python deps** — TRIDENT and PANTHER pin
  conflicting versions in the one shared venv. Fallback: give TRIDENT its own venv in the
  Dockerfile and point `TRIDENT_PYTHON` at it (the app already supports a separate
  interpreter); keep PANTHER in the default venv.
- **`could not select device driver "nvidia"`** — NVIDIA Container Toolkit not installed
  or Docker not restarted (step 1.3).
- **`Path is outside the allowed roots` / empty browser** — `TRIDENT_ALLOWED_ROOTS` must
  list **container** paths (`/data`), not host paths.
- **`uni` weights fail to download / 401** — gated model; set `HF_TOKEN` and accept the
  model license on HuggingFace. `phikon` is not gated.
- **Slow every restart re-downloading weights** — `HF_HOME` (`/state/hf_cache`) volume not
  mounted or `STATE_DIR` changed.
- **Fonts look different offline** — the UI pulls Figtree/JetBrains Mono from Google Fonts;
  the app works fully without them, just with system-font fallback.
