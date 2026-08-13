#!/usr/bin/env bash
# Thin wrapper around PANTHER's prototype trainer.
#
# The backend handles cwd (`${PANTHER_REPO_PATH}/src`) and env (`CUDA_VISIBLE_DEVICES=0`)
# before invoking this script — the script itself is intentionally minimal so the
# exact `python -m training.main_prototype ...` invocation matches the upstream README.

set -euo pipefail

exec python -m training.main_prototype "$@"
