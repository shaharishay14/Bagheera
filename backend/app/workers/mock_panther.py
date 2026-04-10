"""Mock PANTHER model.

Real PANTHER will be swapped in later. Keep this module's surface area minimal:
``run(job)`` is the only entry point the worker imports.
"""
import json
import random
import time
from dataclasses import dataclass


# Tunable from tests via monkeypatch — keep these as module-level globals,
# not constants, so tests can shrink the sleep range.
SLEEP_MIN_SECONDS = 5.0
SLEEP_MAX_SECONDS = 15.0
ERROR_PROBABILITY = 0.10


@dataclass
class MockClusterOutput:
    label: str
    patches_json: str


def run(num_clusters: int) -> list[MockClusterOutput]:
    """Pretend to run PANTHER. Sleeps, ~10% of the time raises, otherwise returns fake clusters."""
    delay = random.uniform(SLEEP_MIN_SECONDS, SLEEP_MAX_SECONDS)
    time.sleep(delay)
    if random.random() < ERROR_PROBABILITY:
        raise RuntimeError("mock panther failure (simulated GPU error)")
    return [
        MockClusterOutput(
            label=f"cluster_{i}",
            patches_json=json.dumps([f"/mock/patches/cluster_{i}_patch_{k}.png" for k in range(4)]),
        )
        for i in range(num_clusters)
    ]
