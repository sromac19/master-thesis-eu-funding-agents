from __future__ import annotations

import hashlib

INITIAL_ROUND = "initial"
REPEAT_ROUND = "repeat"
REPEAT_PAIR_COUNT = 40
REPEAT_SEED = 42


def select_repeat_pairs(
    candidates: list[dict[str, str]],
    *,
    count: int = REPEAT_PAIR_COUNT,
    seed: int = REPEAT_SEED,
) -> list[dict[str, str]]:
    """Select a stable blinded subset for a test-retest consistency check."""
    if count < 1:
        raise ValueError("repeat pair count must be positive")
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for row in candidates:
        key = (row["profile_id"], row["call_id"])
        if key in unique:
            raise ValueError("candidate pool contains duplicate profile-call pairs")
        unique[key] = row
    if count > len(unique):
        raise ValueError("repeat pair count exceeds candidate pool size")
    return sorted(
        unique.values(),
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['profile_id']}:{row['call_id']}".encode()
        ).hexdigest(),
    )[:count]
