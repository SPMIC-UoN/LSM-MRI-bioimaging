"""Intensity normalisation.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from .shells import detect_shell_blocks

NormMode = Literal["global", "voxelwise"]


def b0_mean_volume(
    image_4d: np.ndarray, bvals: np.ndarray, b0_threshold: float = 50.0
) -> np.ndarray:
    """Mean 3D volume across this block's own b0 (bval < threshold)
    volumes. `bvals` must be in the same volume order as `image_4d`'s last
    axis."""
    bvals = np.asarray(bvals)
    b0_mask = bvals < b0_threshold
    if not np.any(b0_mask):
        raise ValueError(f"no b0 volumes found (bval < {b0_threshold}) in this block")
    return image_4d[..., b0_mask].mean(axis=-1)


def normalise_shell(
    image_4d: np.ndarray,
    bvals: np.ndarray,
    reference_b0_mean: np.ndarray,
    mask: np.ndarray | None = None,
    mode: NormMode = "global",
    b0_threshold: float = 50.0,
) -> np.ndarray:
    """Divide `image_4d` by the ratio of its own b0 level to
    `reference_b0_mean`.

    mode="global": one scalar ratio for the whole block (default).
    mode="voxelwise": a per-voxel ratio map.
    """
    own_b0_mean = b0_mean_volume(image_4d, bvals, b0_threshold)

    if mode == "global":
        own_avg = own_b0_mean[mask].mean() if mask is not None else own_b0_mean.mean()
        ref_avg = reference_b0_mean[mask].mean() if mask is not None else reference_b0_mean.mean()
        ratio = own_avg / ref_avg
        return image_4d / ratio
    elif mode == "voxelwise":
        ratio = own_b0_mean / reference_b0_mean
        return image_4d / ratio[..., None]
    raise ValueError(f"unknown normalisation mode: {mode!r}")


def normalise_merged(
    image_4d: np.ndarray,
    bvals: np.ndarray,
    reference_block_index: int = 0,
    mask: np.ndarray | None = None,
    mode: NormMode = "global",
    b0_threshold: float = 50.0,
) -> np.ndarray:
    """Detects shell blocks from `bvals` (shells.detect_shell_blocks) and
    normalises each one against `reference_block_index`'s (default: the
    first shell acquired) b0 level - the orchestration `preprocess()`
    (pipeline.py) actually calls, operating on the whole already-merged
    4D array at once."""
    blocks = detect_shell_blocks(bvals, b0_threshold)
    ref_start, ref_end = blocks[reference_block_index]
    reference_b0_mean = b0_mean_volume(
        image_4d[..., ref_start:ref_end], bvals[ref_start:ref_end], b0_threshold
    )

    out = np.empty_like(image_4d)
    for start, end in blocks:
        out[..., start:end] = normalise_shell(
            image_4d[..., start:end],
            bvals[start:end],
            reference_b0_mean,
            mask,
            mode,
            b0_threshold,
        )
    return out
