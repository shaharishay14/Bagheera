#!/usr/bin/env bash
# Wrapper that forwards named args to TRIDENT's run_batch_of_slides.py.
#
# Required env:
#   TRIDENT_REPO_PATH   absolute path to a checkout of https://github.com/mahmoodlab/TRIDENT
# Optional env:
#   TRIDENT_PYTHON      python interpreter to use (default: python)
#
# Expected args (all required):
#   --task <feat>
#   --wsi_dir <path>
#   --job_dir <path>
#   --patch_encoder <uni_v1|uni_v2|phikon|phikon_v2>
#   --mag <int>
#   --patch_size <int>

set -euo pipefail

if [[ -z "${TRIDENT_REPO_PATH:-}" ]]; then
  echo "TRIDENT_REPO_PATH is not set. Point it at a TRIDENT checkout." >&2
  exit 2
fi

PY="${TRIDENT_PYTHON:-python}"
SCRIPT="${TRIDENT_REPO_PATH}/run_batch_of_slides.py"

if [[ ! -f "$SCRIPT" ]]; then
  echo "run_batch_of_slides.py not found at $SCRIPT" >&2
  exit 2
fi

exec "$PY" "$SCRIPT" "$@"
