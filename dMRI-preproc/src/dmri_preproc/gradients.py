"""FSL-format bval/bvec sidecar I/O.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def fix_nan_bvecs(bvecs: np.ndarray) -> np.ndarray:
    """Replace NaNs (e.g. from EDDY rotating a zero-length b0 bvec) with 0."""
    return np.nan_to_num(np.asarray(bvecs, dtype=float), nan=0.0)


def read_fsl_bval(path: str | Path) -> np.ndarray:
    return np.loadtxt(path).reshape(-1)


def write_fsl_bval(path: str | Path, bvals: np.ndarray) -> None:
    np.savetxt(path, np.asarray(bvals).reshape(1, -1), fmt="%.6f")


def read_fsl_bvec(path: str | Path) -> np.ndarray:
    """FSL bvec files are (3, N) text; returns (N, 3)."""
    return np.loadtxt(path).T


def write_fsl_bvec(path: str | Path, bvecs: np.ndarray) -> None:
    """bvecs: (N, 3) -> written as FSL's (3, N) text format."""
    np.savetxt(path, np.asarray(bvecs).T, fmt="%.6f")
