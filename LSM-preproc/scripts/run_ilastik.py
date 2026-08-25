#!/usr/bin/env python3
"""
Step 2a: Run ilastik segmentation on C00 (GFAP) channel slices.

This script extracts slices from the HDF5 volume and runs ilastik headless
segmentation to produce foreground/background masks.

Features:
  - Retry logic: retries failed slices up to 3 times
  - Failed slice logging: records permanently failed slices for rescue runs
  - Dry run mode: preview what would be done without executing

Usage:
    python run_ilastik.py --strain BXTA_1p3c_NeuN_GFAP
    python run_ilastik.py --strain BXTA_1p3c_NeuN_GFAP --slice-range 0 100
    python run_ilastik.py --strain BXTA_1p3c_NeuN_GFAP --dry-run
    python run_ilastik.py --rescue /path/to/failed_slices.txt
"""

import multiprocessing
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import h5py
import numpy as np
import tifffile
from tqdm import tqdm

ILASTIK_RAM_MB = 64000
ILASTIK_PROJECT = "/gpfs01/imgshare/RodentMRI/WT_BioImaging_2026/scripts/gfap.ilp"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

def get_h5_shape(h5_path: Path) -> tuple:
    """Get the shape of the volume in an HDF5 file."""
    with h5py.File(h5_path, 'r') as f:
        return f['volume'].shape


def extract_slice(h5_path: Path, slice_idx: int) -> np.ndarray:
    """Extract a single Z-slice from the HDF5 volume."""
    with h5py.File(h5_path, 'r') as f:
        return np.array(f['volume'][slice_idx, :, :])


def run_ilastik_on_slice(input_tif: Path, output_dir: Path,
                         project: Path = ILASTIK_PROJECT,
                         ram_mb: int = ILASTIK_RAM_MB) -> Tuple[bool, str]:
    """
    Run ilastik headless on a single slice.

    Args:
        input_tif: Path to input TIFF slice
        output_dir: Directory for output segmentation
        project: Path to ilastik project file (.ilp)
        ram_mb: RAM limit in MB

    Returns:
        Tuple of (success: bool, error_message: str)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "run_ilastik.sh",
        "--headless",
        f"--project={project}",
        "--output_format=tiff",
        '--export_source=Simple Segmentation',
        f"--output_filename_format={output_dir}/{{nickname}}_{{result_type}}.tiff",
        str(input_tif)
    ]

    env = os.environ.copy()
    env['LAZYFLOW_TOTAL_RAM_MB'] = str(ram_mb)

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800  # 30 min/slice: these 4x slices (~15k x 9.5k px) take ~7-8 min
        )

        if result.returncode != 0:
            return False, f"Exit code {result.returncode}: {result.stderr[-3000:]}"
        return True, ""

    except subprocess.TimeoutExpired:
        return False, "Timeout (>30 minutes)"
    except Exception as e:
        return False, str(e)


def run_ilastik_with_retry(input_tif: Path, output_dir: Path,
                           slice_idx: int,
                           max_retries: int = MAX_RETRIES) -> Tuple[bool, str]:
    """
    Run ilastik with retry logic.

    Args:
        input_tif: Path to input TIFF slice
        output_dir: Directory for output segmentation
        slice_idx: Slice index (for logging)
        max_retries: Maximum number of retry attempts

    Returns:
        Tuple of (success: bool, final_error_message: str)
    """
    last_error = ""

    for attempt in range(1, max_retries + 1):
        success, error = run_ilastik_on_slice(input_tif, output_dir)

        if success:
            return True, ""

        last_error = error
        if attempt < max_retries:
            print(f"  Slice {slice_idx}: Attempt {attempt}/{max_retries} failed: {error}")
            print(f"  Retrying in {RETRY_DELAY_SECONDS} seconds...")
            time.sleep(RETRY_DELAY_SECONDS)

    return False, last_error


def log_failed_slice(log_file: Path, h5_path: Path, slice_idx: int, error: str):
    """Append a failed slice to the log file."""
    timestamp = datetime.now().isoformat()
    with open(log_file, 'a') as f:
        f.write(f"{timestamp}\t{h5_path}\t{slice_idx}\t{error}\n")


def load_rescue_slices(rescue_file: Path) -> List[Tuple[Path, int]]:
    """Load slices to rescue from a failed slices log file."""
    slices = []
    with open(rescue_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 3:
                h5_path = Path(parts[1])
                slice_idx = int(parts[2])
                slices.append((h5_path, slice_idx))
    return slices


def _process_single_slice(
    h5_path: Path,
    slice_idx: int,
    output_dir: Path,
    slice_dir: Path,
    skip_existing: bool,
    ) -> Tuple[str, int, Optional[str]]:
    """Process one slice and return a status tuple for the parent to aggregate."""
    output_pattern = output_dir / f"slice_{slice_idx:04d}_Simple Segmentation.tiff"
    if skip_existing and output_pattern.exists():
        return "skip", slice_idx, None

    slice_tif = slice_dir / f"slice_{slice_idx:04d}.tif"
    try:
        slice_data = extract_slice(h5_path, slice_idx)
        tifffile.imwrite(slice_tif, slice_data)
    except Exception as e:
        return "extract_fail", slice_idx, f"extract/write: {e}"

    try:
        success, error = run_ilastik_with_retry(slice_tif, output_dir, slice_idx)
    finally:
        try:
            slice_tif.unlink()
        except OSError:
            pass

    if success:
        return "done", slice_idx, None
    return "failed", slice_idx, error


def _process_single_slice_task(
    task: Tuple[Path, int, Path, Path, bool]
) -> Tuple[str, int, Optional[str]]:
    """Unpack a per-slice task for use with multiprocessing work queues."""
    return _process_single_slice(*task)


def process_ilastik(h5_path, slice_range: tuple = None,
                    skip_existing: bool = True, dry_run: bool = False,
                    n_processes: int = 1) -> Tuple[int, int]:
    """
    Process C00 channel for a strain using ilastik.

    Args:
        h5_path: Path to the H5 file
        slice_range: Optional (start, end) slice range
        skip_existing: Skip slices that already have segmentation
        dry_run: If True, only print what would be done
        n_processes: Number of worker processes to use across slices

    Returns:
        Tuple of (processed_count, failed_count)
    """
    h5_path = Path(h5_path)
    print(f"{'[DRY RUN] ' if dry_run else ''}Processing: {h5_path}")

    # Get volume shape
    shape = get_h5_shape(h5_path)
    n_slices = shape[0]
    print(f"Volume shape: {shape}")

    # Determine slice range
    if slice_range is None:
        start_slice, end_slice = 0, n_slices
    elif isinstance(slice_range, int):
        # process slices for this process index out of n_processes
        process_idx = slice_range
        slices_per_process = n_slices // n_processes
        start_slice = process_idx * slices_per_process
        end_slice = (process_idx + 1) * slices_per_process if process_idx < n_processes - 1 else n_slices
        print(f"Process {process_idx}/{n_processes}: Processing slices {start_slice} to {end_slice}")
        n_processes = 1  # force single process for this slice range
    else:
        start_slice, end_slice = slice_range
        end_slice = min(end_slice, n_slices)

    # Setup output directories
    base_dir = h5_path.parent / h5_path.stem  # e.g., .../session_C00/
    saf_dir = base_dir / "saf"
    slice_dir = saf_dir / "slices"
    output_dir = saf_dir / "outputs"
    failed_log = saf_dir / "failed_slices.txt"

    if not dry_run:
        slice_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output directory: {output_dir}")
    print(f"Failed slices log: {failed_log}")
    print(f"Processing slices {start_slice} to {end_slice}")

    if n_processes < 1:
        raise ValueError("n_processes must be at least 1")

    slice_indices = list(range(start_slice, end_slice))

    if dry_run:
        # Count how many would be processed
        would_process = 0
        would_skip = 0
        for z in slice_indices:
            output_pattern = output_dir / f"slice_{z:04d}_Simple Segmentation.tiff"
            if skip_existing and output_pattern.exists():
                would_skip += 1
            else:
                would_process += 1
        print(f"  Would process: {would_process} slices")
        print(f"  Would skip (existing): {would_skip} slices")
        return would_process, 0

    processed = 0
    failed = 0
    tasks = [
        (h5_path, slice_idx, output_dir, slice_dir, skip_existing)
        for slice_idx in slice_indices
    ]

    if n_processes == 1 or len(slice_indices) <= 1:
        result_iter = (_process_single_slice_task(task) for task in tasks)
        pbar = tqdm(result_iter, total=len(tasks), desc="Processing slices")
    else:
        worker_count = min(n_processes, len(tasks))
        print(f"Using {worker_count} worker processes with dynamic scheduling")
        pool = multiprocessing.Pool(processes=worker_count)
        result_iter = pool.imap_unordered(_process_single_slice_task, tasks, chunksize=1)
        pbar = tqdm(result_iter, total=len(tasks), desc="Processing slices")

    try:
        for status, slice_idx, error in pbar:
            if status == "skip":
                pbar.set_postfix(status="skip")
                continue

            if status == "done":
                processed += 1
                pbar.set_postfix(status="done")
                continue

            failed += 1
            if status == "extract_fail":
                pbar.set_postfix(status="EXTRACT_FAIL")
                print(f"\n  FAILED slice {slice_idx} (extract/write): {error}")
            else:
                pbar.set_postfix(status="FAILED")
                print(f"\n  FAILED slice {slice_idx} after {MAX_RETRIES} attempts: {error}")
            log_failed_slice(failed_log, h5_path, slice_idx, error or "unknown error")
    finally:
        if n_processes > 1 and len(slice_indices) > 1:
            pool.close()
            pool.join()

    print(f"\nSegmentation complete. Outputs in: {output_dir}")
    print(f"  Processed: {processed}, Failed: {failed}")

    if failed > 0:
        print(f"\n  WARNING: {failed} slices failed. See: {failed_log}")
        print(f"  To rescue, run: python run_ilastik.py --rescue {failed_log}")

    return processed, failed


def rescue_failed_slices(rescue_file: Path, skip_existing: bool = True,
                         dry_run: bool = False) -> Tuple[int, int]:
    """
    Re-process slices from a failed slices log file.

    Args:
        rescue_file: Path to failed_slices.txt
        skip_existing: Skip slices that now exist
        dry_run: If True, only print what would be done

    Returns:
        Tuple of (processed_count, failed_count)
    """
    print(f"{'[DRY RUN] ' if dry_run else ''}Rescuing failed slices from: {rescue_file}")

    slices = load_rescue_slices(rescue_file)
    print(f"Found {len(slices)} slices to rescue")

    if dry_run:
        for h5_path, slice_idx in slices:
            print(f"  Would retry: {h5_path} slice {slice_idx}")
        return len(slices), 0

    processed = 0
    still_failed = 0

    # Create new failed log for this rescue run
    rescue_failed_log = rescue_file.parent / f"failed_slices_rescue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    for h5_path, slice_idx in tqdm(slices, desc="Rescuing slices"):
        # Setup paths
        base_dir = h5_path.parent / h5_path.stem
        saf_dir = base_dir / "saf"
        slice_dir = saf_dir / "slices"
        output_dir = saf_dir / "outputs"

        output_pattern = output_dir / f"slice_{slice_idx:04d}_Simple Segmentation.tiff"
        if skip_existing and output_pattern.exists():
            print(f"  Slice {slice_idx}: Already exists, skipping")
            continue

        # Extract and save slice
        slice_data = extract_slice(h5_path, slice_idx)
        slice_tif = slice_dir / f"slice_{slice_idx:04d}.tif"
        tifffile.imwrite(slice_tif, slice_data)

        # Run ilastik with retry
        success, error = run_ilastik_with_retry(slice_tif, output_dir, slice_idx)

        if success:
            processed += 1
            print(f"  Slice {slice_idx}: SUCCESS")
        else:
            still_failed += 1
            print(f"  Slice {slice_idx}: STILL FAILED - {error}")
            log_failed_slice(rescue_failed_log, h5_path, slice_idx, error)

    print(f"\nRescue complete. Processed: {processed}, Still failed: {still_failed}")

    if still_failed > 0:
        print(f"  Remaining failures logged to: {rescue_failed_log}")

    return processed, still_failed


def run_ilastik(dataset, slice_range, dry_run=False, rescue=False, force=False):
   
    if dry_run:
        print("\n*** DRY RUN MODE - No files will be modified ***\n")

    # Rescue mode
    if rescue:
        rescue_failed_slices(rescue, skip_existing=not force, dry_run=dry_run)
        return

    #p, f = process_strain(dataset['strain'], dataset.get('session', ''), slice_range,
    #                      skip_existing=not force,
    #                      dry_run=dry_run)
    print(dataset)
