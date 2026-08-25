#!/usr/bin/env python3
"""
Step 2b: Run Cellpose cell counting on C01 (NeuN) channel.

This script processes the HDF5 volume in blocks, runs Cellpose 2D segmentation
on each Z-slice, extracts cell centroids, and accumulates downsampled cell count maps.

Usage:
    python run_cellpose.py --h5 /path/to/file_C01.h5
    python run_cellpose.py --h5 /path/to/file_C01.h5 --block-range 0 150
    python run_cellpose.py --strain BXTA_1p3c_NeuN_GFAP
"""

import sys
import multiprocessing
from pathlib import Path
from typing import Tuple, List, Optional, Iterable, Any

import h5py
import numpy as np
from skimage.measure import regionprops
from tqdm import tqdm

# Cellpose model paths
CELLPOSE_MODEL_C01 = "/gpfs01/imgshare/RodentMRI/WT_BioImaging_2026/scripts/CP_20251011_151301"

# Cellpose processing parameters
CELLPOSE_BLOCK_SIZE = (64, 512, 512)
CELLPOSE_HALO = (0, 0, 0)
DS_PARAMETER_MAPS = (8, 32, 32)

_CELLPOSE_MODEL: Optional[Any] = None

def ceil_div(a: int, b: int) -> int:
    """Ceiling division."""
    return (a + b - 1) // b


def iter_blocks(shape: Tuple[int, int, int],
                block_size: Tuple[int, int, int],
                halo: Tuple[int, int, int] = (0, 0, 0)
                ) -> Iterable[Tuple]:
    """
    Yield block coordinates for processing.

    Returns tuples of:
        (z0, z1, y0, y1, x0, x1, zz0, zz1, yy0, yy1, xx0, xx1)
    where (z0,z1,y0,y1,x0,x1) is the core block and
    (zz0,zz1,yy0,yy1,xx0,xx1) is the haloed region to load.
    """
    Z, Y, X = shape
    bz, by, bx = block_size
    hz, hy, hx = halo

    for z0 in range(0, Z, bz):
        for y0 in range(0, Y, by):
            for x0 in range(0, X, bx):
                z1 = min(z0 + bz, Z)
                y1 = min(y0 + by, Y)
                x1 = min(x0 + bx, X)

                # Haloed region
                zz0 = max(0, z0 - hz)
                zz1 = min(Z, z1 + hz)
                yy0 = max(0, y0 - hy)
                yy1 = min(Y, y1 + hy)
                xx0 = max(0, x0 - hx)
                xx1 = min(X, x1 + hx)

                yield (z0, z1, y0, y1, x0, x1, zz0, zz1, yy0, yy1, xx0, xx1)


def add_to_bins(counts: np.ndarray, centroids: List[Tuple[float, float, float]],
                bin_size: Tuple[int, int, int]) -> None:
    """Add cell centroids to downsampled count map."""
    if not centroids:
        return

    cz, cy, cx = bin_size
    zyx = np.asarray(centroids, dtype=np.float32)

    zb = np.minimum((zyx[:, 0] // cz).astype(np.int64), counts.shape[0] - 1)
    yb = np.minimum((zyx[:, 1] // cy).astype(np.int64), counts.shape[1] - 1)
    xb = np.minimum((zyx[:, 2] // cx).astype(np.int64), counts.shape[2] - 1)

    np.add.at(counts, (zb, yb, xb), 1)


def run_cellpose_2d(model, vol: np.ndarray) -> np.ndarray:
    """
    Run Cellpose 2D on each Z-slice of the volume.

    Args:
        model: Cellpose model
        vol: Volume with shape (C, Z, Y, X) or (Z, Y, X)

    Returns:
        Mask volume with shape (Z, Y, X)
    """
    if vol.ndim == 4:
        vol = vol[0]  # Take first channel

    vol_mask = np.zeros_like(vol, dtype=np.uint32)

    for z in range(vol.shape[0]):
        slice_data = vol[z, :, :]

        # Add channel dimension for cellpose
        masks, _, _ = model.eval(
            [slice_data[np.newaxis, :, :]],
            do_3D=False,
            channel_axis=0,
            flow_threshold=4,
            cellprob_threshold=-1,
            normalize={'tile_norm_blocksize': 256}
        )

        # Accumulate masks with unique labels
        acc_mask = masks[0].copy().astype(np.uint32)
        if acc_mask.max() > 0:
            acc_mask[acc_mask > 0] = acc_mask[acc_mask > 0] + vol_mask.max()
        vol_mask[z, :, :] = acc_mask

    return vol_mask


def _get_cellpose_model():
    """Lazy-load a per-process Cellpose model instance."""
    global _CELLPOSE_MODEL
    if _CELLPOSE_MODEL is None:
        from cellpose import models

        _CELLPOSE_MODEL = models.CellposeModel(
            gpu=True,
            pretrained_model=CELLPOSE_MODEL_C01
        )
    return _CELLPOSE_MODEL


def _process_block_task(
    task: Tuple[Path, int, Tuple[int, ...], Path]
) -> Tuple[str, int, int]:
    """Process one block and return (status, block_idx, detected_cells)."""
    h5_path, block_idx, block_coords, output_dir = task
    count_file = output_dir / f"cell_counts_block_{block_idx:06d}.npy"

    if count_file.exists():
        return "skipped", block_idx, 0

    (z0, z1, y0, y1, x0, x1, zz0, zz1, yy0, yy1, xx0, xx1) = block_coords

    with h5py.File(h5_path, 'r') as f:
        vol = np.array(f['volume'][zz0:zz1, yy0:yy1, xx0:xx1])

    empty_centroids = np.zeros((0, 3), dtype=np.float32)
    if np.max(vol) < 1000:
        np.save(count_file, empty_centroids)
        return "empty", block_idx, 0

    vol = vol[np.newaxis, ...]
    model = _get_cellpose_model()
    masks = run_cellpose_2d(model, vol)

    core_local = (
        slice(z0 - zz0, z1 - zz0),
        slice(y0 - yy0, y1 - yy0),
        slice(x0 - xx0, x1 - xx0)
    )
    core_masks = masks[core_local]

    if np.max(core_masks) > 1:
        props = regionprops(core_masks.astype(np.int32))
        centroids_global = np.array(
            [(p.centroid[0] + z0, p.centroid[1] + y0, p.centroid[2] + x0)
             for p in props],
            dtype=np.float32,
        )
        if centroids_global.size == 0:
            centroids_global = empty_centroids
    else:
        centroids_global = empty_centroids

    np.save(count_file, centroids_global)
    return "processed", block_idx, len(centroids_global)


def process_cellpose(h5_path: Path,
                   block_size: Tuple[int, int, int] = CELLPOSE_BLOCK_SIZE,
                   halo: Tuple[int, int, int] = CELLPOSE_HALO,
                   bin_size: Tuple[int, int, int] = DS_PARAMETER_MAPS,
                   block_range: Optional[Tuple[int, int]] = None,
                   output_dir: Optional[Path] = None,
                   array_idx: int = 0,
                   n_array: int = 1,
                   n_workers: int = 1):
    """
    Process a volume with Cellpose to count cells.

    Args:
        h5_path: Path to HDF5 file
        block_size: Processing block size (Z, Y, X)
        halo: Overlap for blocks
        bin_size: Downsampling size for output count map
        block_range: Optional (start, end) block indices to process
        output_dir: Output directory (default: derived from h5_path)
        n_workers: Number of worker processes for dynamic block scheduling
    """
    if n_workers < 1:
        raise ValueError("n_workers must be at least 1")

    # Get volume shape
    h5_path = Path(h5_path)
    with h5py.File(h5_path, 'r') as f:
        shape = f['volume'].shape

    Z, Y, X = shape
    print(f"Volume shape: {shape}")

    # Build processing plan
    plan = list(iter_blocks(shape, block_size, halo))
    n_blocks = len(plan)
    print(f"Total blocks: {n_blocks}")

    # Determine block range
    if block_range is None:
        # process blocks for this process index out of n_workers
        blocks_per_process = ceil_div(n_blocks, n_array)
        start_block = array_idx * blocks_per_process
        end_block = min((array_idx + 1) * blocks_per_process, n_blocks)
        print(f"Process {array_idx}/{n_array}: Processing blocks {start_block} to {end_block}")
    else:
        start_block, end_block = block_range
        end_block = min(end_block, n_blocks)

    print(f"Processing blocks {start_block} to {end_block}")

    # Setup output directory
    if output_dir is None:
        base_dir = h5_path.parent / h5_path.stem
        output_dir = base_dir / "cellpose3_2d_outputs"
        output_dir = output_dir / f"bs{block_size[0]}_{block_size[1]}_{block_size[2]}-vs{bin_size[0]}_{bin_size[1]}_{bin_size[2]}"

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Process blocks. Each block stores the GLOBAL (z, y, x) centroids of the
    # cells detected in its core region as a float32 (N, 3) array. Binning into
    # the summary grid happens at stitch time, so:
    #   - the summary resolution is decoupled from segmentation, and
    #   - per-block files stay tiny (proportional to #cells, not grid size),
    # which is essential at fine summary resolutions (a full grid per block
    # would otherwise blow up to ~TB across all blocks).
    selected_blocks = list(range(start_block, end_block))
    tasks = [
        (h5_path, block_idx, plan[block_idx], output_dir)
        for block_idx in selected_blocks
    ]

    if n_workers == 1 or len(tasks) <= 1:
        print(f"Loading model: {CELLPOSE_MODEL_C01}")
        _get_cellpose_model()
        result_iter = (_process_block_task(task) for task in tasks)
        pbar = tqdm(result_iter, total=len(tasks), desc="Processing blocks")
    else:
        worker_count = min(n_workers, len(tasks))
        print(f"Using {worker_count} worker processes with dynamic scheduling")
        pool = multiprocessing.Pool(processes=worker_count)
        result_iter = pool.imap_unordered(_process_block_task, tasks, chunksize=1)
        pbar = tqdm(result_iter, total=len(tasks), desc="Processing blocks")

    try:
        for status, _block_idx, n_cells in pbar:
            if status == "skipped":
                pbar.set_postfix(status="skipped")
            elif status == "empty":
                pbar.set_postfix(status="empty")
            else:
                pbar.set_postfix(status=f"cells={n_cells}")
    finally:
        if n_workers > 1 and len(tasks) > 1:
            pool.close()
            pool.join()

    print(f"Processing complete. Outputs in: {output_dir}")
