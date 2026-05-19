"""Subprocess execution for the TRIDENT bash wrapper."""
from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.models.schemas import DATASET_NAME_PATTERN

# TODO: switch to async background task with status polling.

BACKEND_DIR = Path(__file__).resolve().parents[2]
WRAPPER_SCRIPT = BACKEND_DIR / "scripts" / "run_trident.sh"

_DATASET_NAME_RE = re.compile(DATASET_NAME_PATTERN)

ENCODER_PATCH_SIZE: dict[str, int] = {
    "uni_v1": 256,
    "uni_v2": 256,
    "phikon": 224,
    "phikon_v2": 224,
}

MAGNIFICATION = 20
TASK = "feat"
JOB_DIR_ROOT = "./trident_processed"


def patch_size_for(encoder: str) -> int:
    return ENCODER_PATCH_SIZE[encoder]


def job_dir_for(dataset_name: str) -> str:
    return f"{JOB_DIR_ROOT}/{dataset_name}"


def output_dir_for(dataset_name: str, encoder: str) -> str:
    return (
        f"{job_dir_for(dataset_name)}/"
        f"{MAGNIFICATION}x_{patch_size_for(encoder)}px_0px_overlap/features_{encoder}"
    )


def build_command(dataset_name: str, wsi_dir: str, encoder: str) -> list[str]:
    # Defense in depth: re-validate dataset_name before it lands in a shell command.
    if not _DATASET_NAME_RE.fullmatch(dataset_name):
        raise ValueError(f"Invalid dataset_name: {dataset_name!r}")
    return [
        "bash",
        str(WRAPPER_SCRIPT),
        "--task",
        TASK,
        "--wsi_dir",
        wsi_dir,
        "--job_dir",
        job_dir_for(dataset_name),
        "--patch_encoder",
        encoder,
        "--mag",
        str(MAGNIFICATION),
        "--patch_size",
        str(patch_size_for(encoder)),
    ]


def render_command(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def execute(cmd: list[str]) -> CommandResult:
    """Run synchronously and capture stdout/stderr."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = proc.communicate()
    return CommandResult(returncode=proc.returncode, stdout=stdout, stderr=stderr)
