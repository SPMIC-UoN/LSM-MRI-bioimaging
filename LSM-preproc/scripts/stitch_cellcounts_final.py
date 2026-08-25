#!/usr/bin/env python3
"""
Stitch cell count maps from Cellpose block outputs.

Aggregates block-wise cell count .npy files into a single volume and
saves as TIFF and reoriented NIfTI.

Examples:
    python stitch_cellcounts.py --folder /path/to/cellpose3_2d_outputs/bs... --ref /path/to/ref.nii.gz
    python stitch_cellcounts.py --strain BXTA_1p3c_NeuN_GFAP --ref /path/to/ref.nii.gz
    python stitch_cellcounts.py --all --processed-data-root /path/to/processed --ref /path/to/ref.nii.gz
    python stitch_cellcounts.py --list --processed-data-root /path/to/processed

Place ``config.py`` in the same directory as this script.
Run ``python stitch_cellcounts.py --help`` for all options.
"""

import argparse
import importlib.util
import re
import sys
import warnings
from pathlib import Path
from typing import List

import h5py
import nibabel as nib
import numpy as np
import tifffile
from tqdm import tqdm

# Load config.py directly from the directory containing this script.
# This avoids depending on a fixed package or repository directory layout.
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.py"

if not CONFIG_FILE.is_file():
    raise FileNotFoundError(
        "Could not find config.py in the same directory as this script.\n"
        f"Expected location: {CONFIG_FILE}"
    )

config_spec = importlib.util.spec_from_file_location(
    "stitch_cellcounts_local_config",
    CONFIG_FILE,
)
if config_spec is None or config_spec.loader is None:
    raise ImportError(f"Could not create an import specification for: {CONFIG_FILE}")

config = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(config)

required_config_values = (
    "PROCESSED_DATA_ROOT",
    "DS_PARAMETER_MAPS",
    "CELLCOUNT_BIN_SIZE",
)
missing_config_values = [
    name for name in required_config_values if not hasattr(config, name)
]
if missing_config_values:
    raise AttributeError(
        f"Missing required value(s) in {CONFIG_FILE}: "
        + ", ".join(missing_config_values)
    )

PROCESSED_DATA_ROOT = Path(config.PROCESSED_DATA_ROOT)
DS_PARAMETER_MAPS = tuple(config.DS_PARAMETER_MAPS)
CELLCOUNT_BIN_SIZE = tuple(config.CELLCOUNT_BIN_SIZE)

# Configuration defaults can still be overridden by command-line options
# where an equivalent option is available.

def find_count_files(folder: Path) -> List[Path]:
    """Find all cell count block files."""
    return sorted(folder.glob("cell_counts_block_*.npy"))


def _ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


def _infer_grid_shape(folder: Path, bin_size: tuple):
    """Summary grid (nz, ny, nx) derived from the matching C01.h5 volume.

    Folder layout: .../{session}_C01/cellpose3_2d_outputs/bs..-vs..
    so the volume is .../{session}_C01.h5 two levels up.
    Returns None if the h5 cannot be located.
    """
    try:
        c01_dir = folder.parent.parent              # {session}_C01
        h5_path = c01_dir.parent / f"{c01_dir.name}.h5"
        if not h5_path.exists():
            return None
        with h5py.File(h5_path, "r") as f:
            Z, Y, X = f["volume"].shape
        return (_ceil_div(Z, bin_size[0]),
                _ceil_div(Y, bin_size[1]),
                _ceil_div(X, bin_size[2]))
    except Exception:
        return None


def stitch_counts(
    folder: Path,
    reference_nii: Path,
    bin_size: tuple = CELLCOUNT_BIN_SIZE,
) -> np.ndarray:
    """
    Bin global Cellpose centroids onto the grid of a reference NIfTI.

    Parameters
    ----------
    folder
        Directory containing cell_counts_block_*.npy files. Each file must
        contain an (N, 3) float array of global (z, y, x) centroids.

    reference_nii
        Reference NIfTI defining the final output dimensions. The reference is
        stored in NIfTI (x, y, z) order, while centroid coordinates and the
        intermediate count volume use (z, y, x) order.

    bin_size
        Centroid binning factors in the HDF5 coordinate system, in
        (z, y, x) order.

    Returns
    -------
    counts
        Count volume in (z, y, x) order. After the existing reorientation,
        its NIfTI dimensions will match the reference image.
    """
    folder = Path(folder)
    reference_nii = Path(reference_nii)

    count_files = find_count_files(folder)
    if not count_files:
        raise FileNotFoundError(
            f"No cell_counts_block_*.npy files found in {folder}"
        )

    if not reference_nii.exists():
        raise FileNotFoundError(
            f"Reference NIfTI does not exist: {reference_nii}"
        )

    # The reference NIfTI is stored in (x, y, z) order.
    ref_img = nib.load(str(reference_nii))

    if len(ref_img.shape) < 3:
        raise ValueError(
            f"Reference must be at least 3D; found shape {ref_img.shape}"
        )

    ref_x, ref_y, ref_z = ref_img.shape[:3]

    # Centroid coordinates and the intermediate volume use (z, y, x).
    grid = (ref_z, ref_y, ref_x)

    bz, by, bx = bin_size

    if bz <= 0 or by <= 0 or bx <= 0:
        raise ValueError(
            f"All bin sizes must be positive; received {bin_size}"
        )

    print(f"Found {len(count_files)} count files")
    print(f"Reference NIfTI: {reference_nii}")
    print(f"Reference shape (x, y, z): {(ref_x, ref_y, ref_z)}")
    print(f"Count grid shape (z, y, x): {grid}")
    print(f"Centroid bin size (z, y, x): {bin_size}")

    counts = np.zeros(grid, dtype=np.uint32)

    total_centroids = 0
    included_centroids = 0
    excluded_centroids = 0

    for count_file in tqdm(count_files, desc="Binning centroids"):
        centroids = np.load(count_file)

        # Empty blocks produced by the current run_cellpose.py have shape (0, 3).
        if centroids.size == 0:
            continue

        # Reject legacy pre-binned 3D count grids.
        if centroids.ndim == 3:
            raise ValueError(
                f"Legacy 3D count grid detected in {count_file}: "
                f"shape={centroids.shape}. This function requires unbinned "
                f"(N, 3) global centroid arrays."
            )

        if centroids.ndim != 2 or centroids.shape[1] != 3:
            raise ValueError(
                f"Invalid centroid array in {count_file}: "
                f"expected shape (N, 3), found {centroids.shape}"
            )

        total_centroids += centroids.shape[0]

        # Convert global HDF5 coordinates to output-bin indices.
        zb = np.floor(centroids[:, 0] / bz).astype(np.int64)
        yb = np.floor(centroids[:, 1] / by).astype(np.int64)
        xb = np.floor(centroids[:, 2] / bx).astype(np.int64)

        # Keep only centroids inside the reference field of view.
        valid = (
            (zb >= 0) & (zb < grid[0]) &
            (yb >= 0) & (yb < grid[1]) &
            (xb >= 0) & (xb < grid[2])
        )

        n_valid = int(np.count_nonzero(valid))
        included_centroids += n_valid
        excluded_centroids += centroids.shape[0] - n_valid

        np.add.at(
            counts,
            (zb[valid], yb[valid], xb[valid]),
            1,
        )

    print(f"Total detected centroids: {total_centroids}")
    print(f"Centroids inside reference: {included_centroids}")
    print(f"Centroids outside reference: {excluded_centroids}")
    print(f"Counts stored in volume: {int(counts.sum())}")
    print(f"Final count-grid shape (z, y, x): {counts.shape}")

    if int(counts.sum()) != included_centroids:
        raise RuntimeError(
            "The sum of the count volume does not equal the number of "
            "included centroids."
        )

    return counts


def save_cellcount_outputs(
    counts: np.ndarray,
    output_dir: Path,
    strain: str,
    reference_nii: Path,
    ds_factor: tuple = DS_PARAMETER_MAPS,
):
    """
    Save cell counts using the dimensions and spatial geometry of a reference.
    """
    output_dir = Path(output_dir)
    reference_nii = Path(reference_nii)

    ds_str = f"ds{ds_factor[0]}x{ds_factor[1]}x{ds_factor[2]}"
    strain_short = strain.replace("_NeuN_GFAP", "")

    # Save the intermediate TIFF in its native (z, y, x) order.
    tif_path = (
        output_dir /
        f"{strain_short}_NeuN_cell_counts_{ds_str}.tif"
    )

    tifffile.imwrite(
        tif_path,
        counts.astype(np.uint32),
        compression="zlib",
    )

    print(f"Saved TIFF: {tif_path}")

    # Convert (z, y, x) to the same (x, y, z) arrangement used previously.
    data_reoriented = np.swapaxes(counts, 0, 2)
    data_reoriented = data_reoriented[::1, ::-1, ::-1]

    reference = nib.load(str(reference_nii))

    if data_reoriented.shape != reference.shape[:3]:
        raise ValueError(
            f"Reoriented count shape {data_reoriented.shape} does not match "
            f"reference shape {reference.shape[:3]}"
        )
    
    # Copy the full reference header.
    output_header = reference.header.copy()
    output_header.set_data_dtype(np.float32)
    
    nii_path = (
        output_dir /
        f"{strain_short}_NeuN_cell_counts_{ds_str}_reoriented.nii.gz"
    )

    # Use exactly the same world-coordinate geometry as the reference.
    nii_img = nib.Nifti1Image(
        data_reoriented.astype(np.float32),
        reference.affine,
        header = output_header,
    )

    nii_img.header.set_xyzt_units(xyz="mm", t="sec")
    #nii_img.set_qform(reference.affine, code=1)
    #nii_img.set_sform(reference.affine, code=1)
    
    # Copy qform, sform, and their original codes exactly.
    ref_qform, ref_qform_code = reference.get_qform(coded=True)
    ref_sform, ref_sform_code = reference.get_sform(coded=True)
    
    nii_img.set_qform(ref_qform, code=int(ref_qform_code))
    nii_img.set_sform(ref_sform, code=int(ref_sform_code))

    nib.save(nii_img, nii_path)

    print(f"Saved NIfTI: {nii_path}")
    print(f"Output shape: {data_reoriented.shape}")
    print(f"Reference affine:\n{reference.affine}")


def extract_strain_from_path(folder: Path) -> str:
    """Extract strain name from folder path."""
    # Pattern: .../STRAIN_NeuN_GFAP/...
    path_str = str(folder)
    match = re.search(r'/([^/]+_NeuN_GFAP)/', path_str)
    if match:
        return match.group(1)
    return "unknown_strain"


def process_folder(
    folder: Path,
    reference_nii: Path,
    ds_factor: tuple,
    output_dir: Path = None,
):
    """Process one Cellpose output folder using a reference NIfTI."""
    print(f"\n{'=' * 60}")
    print(f"Processing: {folder}")
    print(f"Reference:  {reference_nii}")
    print("=" * 60)

    strain = extract_strain_from_path(folder)
    print(f"Strain: {strain}")

    try:
        counts = stitch_counts(
            folder=folder,
            reference_nii=reference_nii,
            bin_size=CELLCOUNT_BIN_SIZE,
        )

        if output_dir is None:
            resolved_output_dir = folder.parent
            warnings.warn(
                "--output-dir was not provided. Outputs will be saved in "
                f"the default directory: {resolved_output_dir}",
                UserWarning,
            )
        else:
            resolved_output_dir = Path(output_dir).expanduser().resolve()

        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {resolved_output_dir}")

        save_cellcount_outputs(
            counts=counts,
            output_dir=resolved_output_dir,
            strain=strain,
            reference_nii=reference_nii,
            ds_factor=ds_factor,
        )

        return True

    except Exception as error:
        print(f"ERROR: {error}")
        return False


def find_all_cellpose_outputs(processed_data_root: Path) -> List[Path]:
    """Find all Cellpose output folders below the selected data root."""
    folders = []
    for folder in processed_data_root.rglob("cellpose3_2d_outputs/bs*"):
        if folder.is_dir() and list(folder.glob("cell_counts_block_*.npy")):
            folders.append(folder)
    return sorted(folders)


def main():
    examples = """
Examples:
  Process one explicitly supplied Cellpose folder:
    %(prog)s --folder /path/to/cellpose3_2d_outputs/bs... \
      --ref /path/to/reference.nii.gz

  Process one strain below a selected processed-data root:
    %(prog)s --strain BXTA_1p3c_NeuN_GFAP \
      --processed-data-root /path/to/processed_data \
      --ref /path/to/reference.nii.gz

  Process every detected Cellpose output and save to a chosen directory:
    %(prog)s --all --processed-data-root /path/to/processed_data \
      --ref /path/to/reference.nii.gz \
      --ds-factor 16 64 64 --output-dir /path/to/output

  List detected Cellpose output folders without processing:
    %(prog)s --list --processed-data-root /path/to/processed_data
"""

    parser = argparse.ArgumentParser(
        description=(
            "Stitch block-wise Cellpose centroid files into TIFF and "
            "reoriented NIfTI cell-count maps."
        ),
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--strain", "-s",
        type=str,
        help=(
            "Strain name to process. The script searches for it below "
            "--processed-data-root."
        ),
    )
    input_group.add_argument(
        "--folder", "-f",
        type=Path,
        help=(
            "Direct path to one Cellpose output folder containing "
            "cell_counts_block_*.npy files. When supplied, "
            "--processed-data-root is not used for input discovery."
        ),
    )
    input_group.add_argument(
        "--all", "-a",
        action="store_true",
        help=(
            "Process every Cellpose output folder found below "
            "--processed-data-root."
        ),
    )
    input_group.add_argument(
        "--list", "-l",
        action="store_true",
        help=(
            "List available Cellpose output folders below "
            "--processed-data-root, then exit. --ref is not required."
        ),
    )

    parser.add_argument(
        "--processed-data-root",
        type=Path,
        default=PROCESSED_DATA_ROOT,
        help=(
            "Root directory used by --strain, --all, and --list. "
            "It is ignored when --folder is supplied. "
            f"Default from config: {PROCESSED_DATA_ROOT}"
        ),
    )
    parser.add_argument(
        "--ref",
        type=Path,
        default=None,
        help=(
            "Reference NIfTI defining the output shape, affine, qform, "
            "sform, and header geometry. Required for processing, but not "
            "for --list."
        ),
    )
    parser.add_argument(
        "--ds-factor",
        type=int,
        nargs=3,
        metavar=("Z", "Y", "X"),
        default=DS_PARAMETER_MAPS,
        help=(
            "Downsampling factor in (z, y, x) order used in output "
            "filenames. This does not change centroid binning. "
            f"Default from config: {tuple(DS_PARAMETER_MAPS)}"
        ),
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help=(
            "Directory in which to save TIFF and NIfTI outputs. If omitted, "
            "each result is saved in the parent of its Cellpose output "
            "folder and a warning is printed."
        ),
    )

    args = parser.parse_args()

    processed_data_root = args.processed_data_root.expanduser().resolve()
    ds_factor = tuple(args.ds_factor)
    if any(value <= 0 for value in ds_factor):
        parser.error("--ds-factor values must all be positive integers")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else None
    )

    print("\nResolved configuration")
    print("-" * 60)
    print(f"Script directory:     {SCRIPT_DIR}")
    print(f"Config file:          {CONFIG_FILE}")
    print(f"Selection mode:       "
          f"{'folder' if args.folder else 'strain' if args.strain else 'all' if args.all else 'list'}")
    print(f"Processed-data root:  {processed_data_root}")
    if args.folder:
        print("Root discovery:       not used because --folder was supplied")
    print(f"Downsampling label:   {ds_factor} (z, y, x)")
    print(f"Centroid bin size:    {tuple(CELLCOUNT_BIN_SIZE)} (z, y, x; config value)")
    print(f"Output directory:     {output_dir if output_dir else 'default per input folder'}")

    if args.list:
        if not processed_data_root.exists():
            parser.error(
                f"--processed-data-root does not exist: {processed_data_root}"
            )
        print("\nSearching for Cellpose output folders...")
        folders = find_all_cellpose_outputs(processed_data_root)
        if not folders:
            print(f"No Cellpose output folders found below: {processed_data_root}")
            return
        print(f"Found {len(folders)} Cellpose output folder(s):")
        for folder in folders:
            count_files = list(folder.glob("cell_counts_block_*.npy"))
            print(f"  {folder}: {len(count_files)} count file(s)")
        return

    if args.ref is None:
        parser.error("--ref is required unless --list is used")

    reference_nii = args.ref.expanduser().resolve()
    if not reference_nii.exists():
        parser.error(f"Reference NIfTI does not exist: {reference_nii}")
    print(f"Reference NIfTI:      {reference_nii}")
    print("-" * 60)

    success_count = 0
    failure_count = 0

    if args.folder:
        folder = args.folder.expanduser().resolve()
        print(f"\nUsing explicitly supplied Cellpose folder: {folder}")
        success = process_folder(
            folder,
            reference_nii,
            ds_factor=ds_factor,
            output_dir=output_dir,
        )
        success_count += int(success)
        failure_count += int(not success)

    elif args.all:
        if not processed_data_root.exists():
            parser.error(
                f"--processed-data-root does not exist: {processed_data_root}"
            )
        print(f"\nSearching below processed-data root: {processed_data_root}")
        folders = find_all_cellpose_outputs(processed_data_root)
        if not folders:
            print("No Cellpose output folders containing count files were found.")
            sys.exit(1)
        print(f"Found {len(folders)} folder(s) to process.")
        for folder in folders:
            success = process_folder(
                folder,
                reference_nii,
                ds_factor=ds_factor,
                output_dir=output_dir,
            )
            success_count += int(success)
            failure_count += int(not success)

    elif args.strain:
        if not processed_data_root.exists():
            parser.error(
                f"--processed-data-root does not exist: {processed_data_root}"
            )
        strain_dir = processed_data_root / args.strain
        print(f"\nSearching for strain below: {strain_dir}")
        output_dirs = sorted(strain_dir.rglob("cellpose3_2d_outputs/bs*"))
        output_dirs = [
            folder for folder in output_dirs
            if folder.is_dir() and list(folder.glob("cell_counts_block_*.npy"))
        ]
        if not output_dirs:
            print(
                f"No Cellpose outputs containing count files were found "
                f"for strain: {args.strain}"
            )
            sys.exit(1)
        print(f"Found {len(output_dirs)} matching folder(s).")
        for folder in output_dirs:
            success = process_folder(
                folder,
                reference_nii,
                ds_factor=ds_factor,
                output_dir=output_dir,
            )
            success_count += int(success)
            failure_count += int(not success)

    print(f"\n{'=' * 60}")
    print("Processing summary")
    print(f"Successful folders: {success_count}")
    print(f"Failed folders:     {failure_count}")
    print("=" * 60)

    if failure_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
