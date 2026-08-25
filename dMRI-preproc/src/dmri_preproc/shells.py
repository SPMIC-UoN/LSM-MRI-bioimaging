"""Shell-block detection from a single merged bval array.
"""

from __future__ import annotations

import numpy as np


def detect_shell_blocks(
    bvals: np.ndarray, b0_threshold: float = 50.0, tol: float = 50.0
) -> list[tuple[int, int]]:
    """Returns [(start, end), ...] half-open index ranges, one per shell,
    covering the whole array in acquisition order. `tol` groups
    near-identical non-b0 bvals (e.g. 999.8 vs 1000.2) into one shell."""
    bvals = np.asarray(bvals, dtype=float)
    n = len(bvals)
    if n == 0:
        raise ValueError("bvals is empty")

    non_b0 = bvals >= b0_threshold
    if not np.any(non_b0):
        raise ValueError(f"no non-b0 volumes found (bval >= {b0_threshold}) - cannot detect shells")

    # every volume's "shell key" = its own bval if non-b0, else its
    # nearest non-b0 neighbour's bval - preferring the NEXT one (see
    # module docstring), falling back to the previous one only for
    # trailing b0s with nothing non-b0 after them.
    keys = np.full(n, np.nan)
    keys[non_b0] = bvals[non_b0]

    nxt = np.nan
    for i in range(n - 1, -1, -1):
        if np.isnan(keys[i]):
            keys[i] = nxt
        else:
            nxt = keys[i]
    last = np.nan
    for i in range(n):
        if np.isnan(keys[i]):
            keys[i] = last
        else:
            last = keys[i]

    blocks = []
    start = 0
    for i in range(1, n):
        if abs(keys[i] - keys[i - 1]) > tol:
            blocks.append((start, i))
            start = i
    blocks.append((start, n))
    return blocks
