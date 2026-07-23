"""In-memory, process-local cache for PANTHER per-slide encoder assignments.

The heavy part of every per-slide visualization is the PANTHER encoder forward
pass (`encoder.representation(...)` inside `visualization._compute_assignments`).
For a single (model, slide) many renderers need the *same* assignments — the
assignment heatmap, the mixture (π_c) plot, the example patches, the per-slide
t-SNE, the ROI tile, and (in the upcoming Compare view) several panels rendered
back-to-back in one session. Re-running the encoder for each is wasteful.

This module memoizes the computed record

    (coords, cluster_labels, qq, mixture_probs, patch_size)

keyed by ``(model_id, slide_stem)``. The key is deliberately scoped to the
model: each trained model has its own prototypes, so assignments are NEVER
shareable across models even for the same slide.

Design notes / invariants:

- **No heavy imports.** The cached arrays are numpy arrays, but they only ever
  pass *through* this module as opaque objects — we never import numpy/torch
  here, so importing this module never pulls in ML deps and the server keeps
  booting on a dev laptop.
- **Bounded LRU.** An ``OrderedDict`` bounded at ``MAX_ENTRIES``; the
  least-recently-used entry is evicted on overflow. Purely in memory — nothing
  survives a process restart.
- **Thread-safe.** A single module-level lock guards the ordered dict. A
  per-key lock lets ``get_or_compute`` compute a miss without holding the
  global lock (so two renders of *different* keys never block each other) while
  still ensuring two concurrent renders of the *same* key compute only once.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable, Optional, Tuple

# Max distinct (model, slide) records held at once. Each record is a handful of
# numpy arrays for one slide, so 32 is a generous ceiling for a single session
# (Compare renders a few slides across a few models) while staying bounded.
MAX_ENTRIES = 32

# A cache record is whatever the compute step returns; the visualization layer
# stores (coords, cluster_labels, qq, mixture_probs, patch_size). We treat it as
# an opaque object here so this module never needs numpy/torch.
Record = Any
Key = Tuple[str, str]

_lock = threading.Lock()
_cache: "OrderedDict[Key, Record]" = OrderedDict()

# Per-key compute locks, so a miss on one key doesn't block renders of other
# keys. Guarded by `_lock` when handed out.
_key_locks: dict[Key, threading.Lock] = {}


def _make_key(model_id: str, slide_stem: str) -> Key:
    return (str(model_id), str(slide_stem))


def get(model_id: str, slide_stem: str) -> Optional[Record]:
    """Return the cached record for ``(model_id, slide_stem)`` or ``None``.

    A hit is marked most-recently-used.
    """
    key = _make_key(model_id, slide_stem)
    with _lock:
        record = _cache.get(key)
        if record is not None:
            _cache.move_to_end(key)
        return record


def put(model_id: str, slide_stem: str, record: Record) -> None:
    """Store ``record`` under ``(model_id, slide_stem)``, evicting LRU on overflow."""
    key = _make_key(model_id, slide_stem)
    with _lock:
        _cache[key] = record
        _cache.move_to_end(key)
        while len(_cache) > MAX_ENTRIES:
            _cache.popitem(last=False)  # evict least-recently-used


def clear_model(model_id: str) -> int:
    """Drop every cached entry belonging to ``model_id``. Returns the count removed.

    Exposed so a model delete / re-render can invalidate stale assignments; no
    current call site requires it.
    """
    mid = str(model_id)
    with _lock:
        stale = [k for k in _cache if k[0] == mid]
        for k in stale:
            del _cache[k]
            _key_locks.pop(k, None)
        return len(stale)


def clear() -> None:
    """Drop the entire cache (mainly for tests)."""
    with _lock:
        _cache.clear()
        _key_locks.clear()


def _key_lock(key: Key) -> threading.Lock:
    with _lock:
        lock = _key_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _key_locks[key] = lock
        return lock


def get_or_compute(
    model_id: str,
    slide_stem: str,
    compute_fn: Callable[[], Record],
) -> Record:
    """Return the cached record, computing + storing it on a miss.

    ``compute_fn`` is a zero-arg callable returning the record. A per-key lock
    ensures two concurrent callers for the *same* key compute only once (the
    second waits, then sees the stored value), while callers for *different*
    keys never block each other.
    """
    hit = get(model_id, slide_stem)
    if hit is not None:
        return hit

    key = _make_key(model_id, slide_stem)
    lock = _key_lock(key)
    with lock:
        # Re-check under the per-key lock: another thread may have computed it
        # while we were waiting to acquire the lock.
        hit = get(model_id, slide_stem)
        if hit is not None:
            return hit
        record = compute_fn()
        put(model_id, slide_stem, record)
        return record
