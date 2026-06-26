"""Subprocess execution for the PANTHER bash wrapper."""
from __future__ import annotations

import gc
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.models.schemas import DATASET_NAME_PATTERN

BACKEND_DIR = Path(__file__).resolve().parents[2]
WRAPPER_SCRIPT = BACKEND_DIR / "scripts" / "run_panther.sh"

_DATASET_NAME_RE = re.compile(DATASET_NAME_PATTERN)

SPLIT_NAMES = "train"
CUDA_VISIBLE_DEVICES = "0"

# PANTHER's main_prototype does `args.split_dir = os.path.join('splits', args.split_dir)`,
# so every split physically lives under
#   ${PANTHER_REPO_PATH}/src/splits/datasets_splits/{dataset}/{split}/k={i}/
# and PANTHER reads the train/val/test CSVs AND writes the prototype .pkl there.
# fold_dir_rel (the --split_dir arg) deliberately OMITS the 'splits/' prefix because
# PANTHER prepends it; the on-disk paths below MUST include it so we write where it reads.
SPLITS_DIR = "splits"
DATASETS_SPLITS_DIR = "datasets_splits"


def panther_src_dir(panther_repo_path: str) -> Path:
    return Path(panther_repo_path) / "src"


def datasets_splits_root_abs(panther_repo_path: str) -> Path:
    return panther_src_dir(panther_repo_path) / SPLITS_DIR / DATASETS_SPLITS_DIR


def dataset_splits_root_abs(panther_repo_path: str, dataset_name: str) -> Path:
    if not _DATASET_NAME_RE.fullmatch(dataset_name):
        raise ValueError(f"Invalid dataset_name: {dataset_name!r}")
    return datasets_splits_root_abs(panther_repo_path) / dataset_name


def kfold_split_dir_abs(panther_repo_path: str, dataset_name: str, split_name: str) -> Path:
    return dataset_splits_root_abs(panther_repo_path, dataset_name) / split_name


def fold_dir_abs(
    panther_repo_path: str, dataset_name: str, split_name: str, fold_index: int
) -> Path:
    return kfold_split_dir_abs(panther_repo_path, dataset_name, split_name) / f"k={fold_index}"


def fold_dir_rel(dataset_name: str, split_name: str, fold_index: int) -> str:
    """Path passed to PANTHER, relative to its src/ cwd."""
    return f"{DATASETS_SPLITS_DIR}/{dataset_name}/{split_name}/k={fold_index}"


FEATS_DIR_NAMES = ("feats_h5", "feats_pt")


def feats_h5_data_source(features_dir: str) -> str:
    """Return a --data_source path PANTHER will accept.

    PANTHER's WSIProtoDataset asserts the data_source dir basename is 'feats_h5'
    or 'feats_pt' (it scans that dir for the .h5/.pt files). TRIDENT names its
    output 'features_{encoder}', so we expose a sibling 'feats_h5' symlink that
    points at the TRIDENT features dir and hand PANTHER that path. Idempotent
    across folds/reruns; falls back to the original dir if the link can't be made.
    """
    feats = Path(features_dir)
    if feats.name in FEATS_DIR_NAMES:
        return str(feats)
    link = feats.parent / "feats_h5"
    try:
        if not (link.is_symlink() or link.exists()):
            link.symlink_to(feats.name)  # relative link within the same parent dir
    except OSError:
        return str(feats)
    return str(link)


@dataclass(frozen=True)
class PantherFoldArgs:
    features_dir: str
    split_dir_rel: str
    mode: str
    in_dim: int
    n_proto_patches: int
    n_proto: int
    n_init: int
    seed: int
    num_workers: int


def build_command(args: PantherFoldArgs) -> list[str]:
    return [
        "bash",
        str(WRAPPER_SCRIPT),
        "--mode",
        args.mode,
        "--data_source",
        args.features_dir,
        "--split_dir",
        args.split_dir_rel,
        "--split_names",
        SPLIT_NAMES,
        "--in_dim",
        str(args.in_dim),
        "--n_proto_patches",
        str(args.n_proto_patches),
        "--n_proto",
        str(args.n_proto),
        "--n_init",
        str(args.n_init),
        "--seed",
        str(args.seed),
        "--num_workers",
        str(args.num_workers),
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


def between_folds_cleanup() -> None:
    """Best-effort cleanup between fold subprocesses.

    The subprocesses are independent OS processes so CUDA state can't leak in
    this process, but a Python-level gc nudge is cheap insurance against
    accumulated file handles / large readers.
    """
    gc.collect()


def scan_prototype_files(prototypes_dir: Path) -> list[str]:
    """Return basenames of .pkl / .pt files emitted by PANTHER under prototypes/."""
    if not prototypes_dir.is_dir():
        return []
    out: list[str] = []
    for entry in sorted(prototypes_dir.iterdir()):
        if entry.is_file() and entry.suffix in {".pkl", ".pt"}:
            out.append(entry.name)
    return out
