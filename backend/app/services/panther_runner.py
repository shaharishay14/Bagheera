"""Subprocess execution for the PANTHER bash wrapper."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.models.schemas import DATASET_NAME_PATTERN, PantherRunRequest

# TODO: switch to async background task with status polling.

BACKEND_DIR = Path(__file__).resolve().parents[2]
WRAPPER_SCRIPT = BACKEND_DIR / "scripts" / "run_panther.sh"

_DATASET_NAME_RE = re.compile(DATASET_NAME_PATTERN)

SPLIT_NAMES = "train"
CUDA_VISIBLE_DEVICES = "0"


def split_dir_rel(dataset_name: str) -> str:
    """Relative split dir as passed to PANTHER (cwd is `${PANTHER_REPO_PATH}/src`)."""
    return f"splits/{dataset_name}"


def panther_src_dir(panther_repo_path: str) -> Path:
    return Path(panther_repo_path) / "src"


def split_dir_abs(panther_repo_path: str, dataset_name: str) -> Path:
    return panther_src_dir(panther_repo_path) / "splits" / dataset_name


def build_command(req: PantherRunRequest, features_dir: str) -> list[str]:
    # Defense in depth — same regex the Pydantic schema applied.
    if not _DATASET_NAME_RE.fullmatch(req.dataset_name):
        raise ValueError(f"Invalid dataset_name: {req.dataset_name!r}")
    return [
        "bash",
        str(WRAPPER_SCRIPT),
        "--mode",
        req.mode,
        "--data_source",
        features_dir,
        "--split_dir",
        split_dir_rel(req.dataset_name),
        "--split_names",
        SPLIT_NAMES,
        "--in_dim",
        str(req.in_dim),
        "--n_proto_patches",
        str(req.n_proto_patches),
        "--n_proto",
        str(req.n_proto),
        "--n_init",
        str(req.n_init),
        "--seed",
        str(req.seed),
        "--num_workers",
        str(req.num_workers),
    ]


def render_command(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def execute(cmd: list[str], *, cwd: Path) -> CommandResult:
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": CUDA_VISIBLE_DEVICES}
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = proc.communicate()
    return CommandResult(returncode=proc.returncode, stdout=stdout, stderr=stderr)
