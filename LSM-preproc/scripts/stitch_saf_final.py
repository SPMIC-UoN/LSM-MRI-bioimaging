#!/usr/bin/env python3
"""
Stitch SAF (Stained Area Fraction) maps from ilastik segmentation outputs.

The script reads ilastik segmentation slices, groups them into z-blocks,
calculates the foreground fraction within each downsampling block, and saves
the resulting SAF volume as TIFF and reoriented NIfTI.

Default values are loaded from config.py located in the same directory as this
script. Command-line arguments can override those defaults.

Examples
--------
Process one SAF output folder:
    python stitch_saf.py \
        --folder /path/to/saf/outputs

Process one folder with custom output directory, downsampling, and voxel size:
    python stitch_saf.py \
        --folder /path/to/saf/outputs \
        --output-dir /path/to/output \
        --ds-factor 8 32 32 \
        --voxel-size 4 1.66 1.66

Process one strain using a custom processed-data root:
    python stitch_saf.py \
        --strain BXTA_1p3c_NeuN_GFAP \
        --processed-data-root /path/to/processed_data

Process all discovered SAF outputs:
    python stitch_saf.py --all

List available SAF output folders:
    python stitch_saf.py --list
"""

import argparse
import importlib.util
import re
import sys
import warnings
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import nibabel as nib
import numpy as np
import tifffile
from tqdm import tqdm


# -------------------------------------------------------------------------
# Load config.py from the same directory as this script
# -------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.py"

if not CONFIG_FILE.exists():
    raise FileNotFoundError(
        "Could not find config.py in the same directory as this script.\n"
        f"Expected config file: {CONFIG_FILE}"
    )

config_spec = importlib.util.spec_from_file_location("local_stitch_saf_config", CONFIG_FILE)

if config_spec is None or config_spec.loader is None:
    raise ImportError(f"Could not load config module from: {CONFIG_FILE}")

config = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(config)

REQUIRED_CONFIG_VALUES = (
    "PROCESSED_DATA_ROOT",
    "DS_PARAMETER_MAPS",
    "VOXEL_SIZE_4X",
)

missing_config_values = [
    name for name in REQUIRED_CONFIG_VALUES if not hasattr(config, name)
]

if missing_config_values:
    raise AttributeError(
        f"The config file {CONFIG_FILE} is missing required value(s): "
        + ", ".join(missing_config_values)
    )

PROCESSED_DATA_ROOT = Path(config.PROCESSED_DATA_ROOT).expanduser()
DS_PARAMETER_MAPS = tuple(int(v) for v in config.DS_PARAMETER_MAPS)
VOXEL_SIZE_4X = tuple(float(v) for v in config.VOXEL_SIZE_4X)

# Fixed ilastik label treated as foreground.
FG_LABEL = 2


def positive_int_triplet(values: Sequence[int], name: str) -> Tuple[int, int, int]:
    """Validate and convert a three-value integer sequence."""
    triplet = tuple(int(v) for v in values)

    if len(triplet) != 3:
        raise ValueError(f"{name} must contain exactly three values: Z Y X")

    if any(v <= 0 for v in triplet):
        raise ValueError(f"{name} values must all be greater than zero: {triplet}")

    return triplet


def positive_float_triplet(
    values: Sequence[float],
    name: str,
) -> Tuple[float, float, float]:
    """Validate and convert a three-value floating-point sequence."""
    triplet = tuple(float(v) for v in values)

    if len(triplet) != 3:
        raise ValueError(f"{name} must contain exactly three values: Z Y X")

    if any(v <= 0 for v in triplet):
        raise ValueError(f"{name} values must all be greater than zero: {triplet}")

    return triplet


def find_segmentation_files(folder: Path) -> List[Tuple[int, Path]]:
    """Find segmentation files and extract their slice indices."""
    pattern = re.compile(
        r"slice_(\d+)_Simple Segmentation\.tiff?$",
        re.IGNORECASE,
    )

    files_with_indices: List[Tuple[int, Path]] = []

    for file_path in folder.iterdir():
        if not file_path.is_file():
            continue

        match = pattern.match(file_path.name)
        if match:
            files_with_indices.append((int(match.group(1)), file_path))

    return sorted(files_with_indices, key=lambda item: item[0])


def check_missing_slices(
    files_with_indices: List[Tuple[int, Path]],
) -> List[int]:
    """Return missing slice indices between the minimum and maximum indices."""
    if not files_with_indices:
        return []

    indices = [idx for idx, _ in files_with_indices]
    expected = set(range(min(indices), max(indices) + 1))
    return sorted(expected - set(indices))


def calculate_saf_chunk(
    slice_stack: np.ndarray,
    ds_factor: Tuple[int, int, int],
    fg_label: int = 2,
) -> np.ndarray:
    """
    Calculate SAF for one 3D block of segmentation slices.

    Parameters
    ----------
    slice_stack
        Segmentation stack in Z, Y, X order.
    ds_factor
        Downsampling block size in Z, Y, X order.
    fg_label
        Segmentation value treated as foreground.

    Returns
    -------
    numpy.ndarray
        Two-dimensional SAF map for the current z-block.
    """
    mask = (slice_stack == fg_label).astype(np.float32)

    _, height, width = mask.shape
    _, ds_y, ds_x = ds_factor

    out_h = (height + ds_y - 1) // ds_y
    out_w = (width + ds_x - 1) // ds_x

    padded_h = out_h * ds_y
    padded_w = out_w * ds_x

    # Foreground fraction at every Y-X pixel across the current z-block.
    mean_mask = mask.mean(axis=0)

    # Edge padding keeps the SAF grid aligned with other downsampled maps.
    if padded_h > height or padded_w > width:
        mean_mask = np.pad(
            mean_mask,
            ((0, padded_h - height), (0, padded_w - width)),
            mode="edge",
        )

    saf = mean_mask.reshape(out_h, ds_y, out_w, ds_x).mean(axis=(1, 3))
    return saf.astype(np.float32)


def stitch_saf(
    segmentation_dir: Path,
    ds_factor: Tuple[int, int, int],
    fg_label: int,
) -> np.ndarray:
    """
    Calculate the SAF volume by processing slices in z-axis chunks.
    """
    print(f"\nSearching for segmentation slices in:\n  {segmentation_dir}")

    files_with_indices = find_segmentation_files(segmentation_dir)

    if not files_with_indices:
        raise FileNotFoundError(
            "No segmentation files matching "
            "'slice_<index>_Simple Segmentation.tif[f]' were found in:\n"
            f"{segmentation_dir}"
        )

    n_slices = len(files_with_indices)
    ds_z, _, _ = ds_factor

    missing = check_missing_slices(files_with_indices)
    if missing:
        preview = ", ".join(str(v) for v in missing[:10])
        suffix = " ..." if len(missing) > 10 else ""
        warnings.warn(
            f"Found {len(missing)} missing slice index/indices: "
            f"{preview}{suffix}",
            UserWarning,
        )

    n_z_blocks = (n_slices + ds_z - 1) // ds_z

    print(f"Found segmentation slices : {n_slices}")
    print(f"Z-blocks to calculate     : {n_z_blocks}")
    print(f"Downsampling factor       : {ds_factor}")
    print(f"Foreground label          : {fg_label}")

    saf_blocks: List[np.ndarray] = []

    for z_block_idx in tqdm(
        range(n_z_blocks),
        desc="Processing z-blocks",
    ):
        start_slice = z_block_idx * ds_z
        end_slice = min((z_block_idx + 1) * ds_z, n_slices)

        slice_stack = []

        for file_position in range(start_slice, end_slice):
            _, file_path = files_with_indices[file_position]
            slice_stack.append(tifffile.imread(file_path))

        stacked_slices = np.stack(slice_stack, axis=0)
        saf_blocks.append(
            calculate_saf_chunk(
                stacked_slices,
                ds_factor=ds_factor,
                fg_label=fg_label,
            )
        )

    saf_volume = np.stack(saf_blocks, axis=0)

    print(f"Calculated SAF volume shape: {saf_volume.shape}")
    return saf_volume


def save_saf_outputs(
    saf_volume: np.ndarray,
    output_dir: Path,
    ds_factor: Tuple[int, int, int],
    voxel_size: Tuple[float, float, float],
) -> Tuple[Path, Path]:
    """
    Save the SAF volume as TIFF and reoriented NIfTI.

    Parameters
    ----------
    saf_volume
        SAF data in Z, Y, X order.
    output_dir
        Directory in which output files will be created.
    ds_factor
        Downsampling factors in Z, Y, X order.
    voxel_size
        Original image voxel size in Z, Y, X order, in micrometres.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    ds_str = f"ds{ds_factor[0]}x{ds_factor[1]}x{ds_factor[2]}"

    tif_path = output_dir / f"saf_{ds_str}.tif"
    tifffile.imwrite(
        tif_path,
        saf_volume.astype(np.float32),
        compression="zlib",
    )
    print(f"Saved TIFF              : {tif_path}")

    # Reorient from Z-Y-X array order into X-Y-Z NIfTI order.
    data_reoriented = np.swapaxes(saf_volume, 0, 2)
    data_reoriented = data_reoriented[::1, ::-1, ::-1]

    # Construct the downsampled voxel dimensions in millimetres.
    affine = np.eye(4, dtype=float)
    affine[0, 0] = voxel_size[2] * ds_factor[2] * 1e-3
    affine[1, 1] = voxel_size[1] * ds_factor[1] * 1e-3
    affine[2, 2] = voxel_size[0] * ds_factor[0] * 1e-3

    nii_path = output_dir / f"saf_{ds_str}_reoriented.nii.gz"
    nii_img = nib.Nifti1Image(
        data_reoriented.astype(np.float32),
        affine,
    )
    nii_img.header.set_xyzt_units(xyz="mm", t="sec")
    nii_img.set_qform(affine, code=1)
    nii_img.set_sform(affine, code=1)
    nib.save(nii_img, nii_path)

    print(f"Saved NIfTI            : {nii_path}")
    print(
        "Output voxel size (mm) : "
        f"({affine[2, 2]:g}, {affine[1, 1]:g}, {affine[0, 0]:g}) "
        "[Z, Y, X]"
    )

    return tif_path, nii_path


def find_strain_saf_outputs(
    strain: str,
    processed_data_root: Path,
) -> List[Path]:
    """Find SAF output folders for one strain."""
    magnitude_dir = (
        processed_data_root
        / strain
        / "4xobj_1p66xzoom_4um_step"
    )

    print(f"\nSearching for strain SAF outputs under:\n  {magnitude_dir}")
    return sorted(magnitude_dir.glob("*C00/saf/outputs"))


def find_all_saf_outputs(processed_data_root: Path) -> List[Path]:
    """Find all SAF output folders under the selected processed-data root."""
    print(f"\nSearching for all SAF outputs under:\n  {processed_data_root}")
    return sorted(processed_data_root.rglob("*C00/saf/outputs"))


def default_output_dir_for_folder(segmentation_dir: Path) -> Path:
    """
    Return the original/default SAF output location.

    For an input folder ending in saf/outputs, this resolves to the parent of
    that saf directory, matching the behaviour of the original script.
    """
    return segmentation_dir.parent.parent


def resolve_output_dir(
    segmentation_dir: Path,
    requested_output_dir: Optional[Path],
    multiple_inputs: bool,
) -> Path:
    """
    Determine the final output directory for one SAF input folder.

    When processing multiple folders with one custom output root, each input is
    written to a separate strain/session-derived subdirectory to avoid filename
    collisions.
    """
    if requested_output_dir is None:
        output_dir = default_output_dir_for_folder(segmentation_dir)
        warnings.warn(
            "--output-dir was not provided. SAF outputs will be saved in the "
            f"default directory:\n{output_dir}",
            UserWarning,
        )
        return output_dir

    requested_output_dir = requested_output_dir.expanduser().resolve()

    if not multiple_inputs:
        return requested_output_dir

    # Preserve enough of the source hierarchy to avoid overwriting outputs
    # when --all or a strain search finds multiple SAF folders.
    session_name = segmentation_dir.parents[2].name
    strain_name = (
        segmentation_dir.parents[4].name
        if len(segmentation_dir.parents) > 4
        else "unknown_strain"
    )

    return requested_output_dir / strain_name / session_name


def process_folder(
    segmentation_dir: Path,
    ds_factor: Tuple[int, int, int],
    voxel_size: Tuple[float, float, float],
    fg_label: int,
    requested_output_dir: Optional[Path],
    multiple_inputs: bool = False,
) -> bool:
    """Process one SAF segmentation output directory."""
    segmentation_dir = segmentation_dir.expanduser().resolve()

    print(f"\n{'=' * 72}")
    print(f"Processing SAF folder:\n  {segmentation_dir}")
    print(f"{'=' * 72}")

    if not segmentation_dir.exists():
        print(f"ERROR: Input folder does not exist:\n  {segmentation_dir}")
        return False

    if not segmentation_dir.is_dir():
        print(f"ERROR: Input path is not a directory:\n  {segmentation_dir}")
        return False

    output_dir = resolve_output_dir(
        segmentation_dir=segmentation_dir,
        requested_output_dir=requested_output_dir,
        multiple_inputs=multiple_inputs,
    )

    print(f"Resolved output directory:\n  {output_dir}")

    try:
        saf_volume = stitch_saf(
            segmentation_dir=segmentation_dir,
            ds_factor=ds_factor,
            fg_label=fg_label,
        )

        save_saf_outputs(
            saf_volume=saf_volume,
            output_dir=output_dir,
            ds_factor=ds_factor,
            voxel_size=voxel_size,
        )

        print("Folder completed successfully.")
        return True

    except Exception as exc:
        print(f"ERROR while processing {segmentation_dir}:\n  {exc}")
        return False


def build_parser() -> argparse.ArgumentParser:
    """Build and return the command-line argument parser."""
    formatter = argparse.RawDescriptionHelpFormatter

    parser = argparse.ArgumentParser(
        description=(
            "Stitch SAF maps from ilastik segmentation outputs.\n\n"
            "Defaults are loaded from config.py located beside this script. "
            "Command-line arguments override those defaults."
        ),
        epilog=(
            "Examples:\n"
            "  python stitch_saf.py --folder /path/to/saf/outputs\n\n"
            "  python stitch_saf.py \\\n"
            "      --folder /path/to/saf/outputs \\\n"
            "      --output-dir /path/to/output \\\n"
            "      --ds-factor 8 32 32 \\\n"
            "      --voxel-size 4 1.66 1.66\n\n"
            "  python stitch_saf.py \\\n"
            "      --strain BXTA_1p3c_NeuN_GFAP \\\n"
            "      --processed-data-root /path/to/processed_data\n\n"
            "  python stitch_saf.py --all\n"
            "  python stitch_saf.py --list"
        ),
        formatter_class=formatter,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)

    mode_group.add_argument(
        "--folder",
        "-f",
        type=Path,
        help=(
            "Direct path to one ilastik saf/outputs folder. When this option "
            "is used, --processed-data-root is not used."
        ),
    )

    mode_group.add_argument(
        "--strain",
        "-s",
        type=str,
        help=(
            "Strain name to process. The script searches beneath "
            "--processed-data-root/<strain>/4xobj_1p66xzoom_4um_step."
        ),
    )

    mode_group.add_argument(
        "--all",
        "-a",
        action="store_true",
        help=(
            "Process every '*C00/saf/outputs' folder found beneath "
            "--processed-data-root."
        ),
    )

    mode_group.add_argument(
        "--list",
        "-l",
        action="store_true",
        help=(
            "List available '*C00/saf/outputs' folders beneath "
            "--processed-data-root without processing them."
        ),
    )

    parser.add_argument(
        "--processed-data-root",
        type=Path,
        default=PROCESSED_DATA_ROOT,
        help=(
            "Root directory used by --strain, --all, and --list. "
            f"Default from config.py: {PROCESSED_DATA_ROOT}"
        ),
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        dest="output_dir",
        type=Path,
        default=None,
        help=(
            "Directory in which TIFF and NIfTI outputs will be saved. "
            "When omitted, the original default output location is used and "
            "a warning is printed. For --all or multiple strain results, this "
            "acts as an output root and separate subdirectories are created."
        ),
    )

    parser.add_argument(
        "--ds-factor",
        dest="ds_factor",
        type=int,
        nargs=3,
        default=DS_PARAMETER_MAPS,
        metavar=("Z", "Y", "X"),
        help=(
            "Downsampling block size in Z Y X order. This controls both the "
            "actual SAF calculation and the output filename. "
            f"Default from config.py: {DS_PARAMETER_MAPS}"
        ),
    )

    parser.add_argument(
        "--voxel-size",
        type=float,
        nargs=3,
        default=VOXEL_SIZE_4X,
        metavar=("Z", "Y", "X"),
        help=(
            "Original image voxel size in micrometres, supplied in Z Y X "
            "order. It is combined with --ds-factor to construct the NIfTI "
            f"affine. Default from config.py: {VOXEL_SIZE_4X}"
        ),
    )

    return parser


def print_configuration(
    args: argparse.Namespace,
    processed_data_root: Path,
    ds_factor: Tuple[int, int, int],
    voxel_size: Tuple[float, float, float],
) -> None:
    """Print the resolved run configuration."""
    if args.folder is not None:
        selection_mode = "single folder"
    elif args.strain is not None:
        selection_mode = f"strain: {args.strain}"
    elif args.all:
        selection_mode = "all discovered folders"
    else:
        selection_mode = "list folders only"

    print("\nResolved configuration")
    print("-" * 72)
    print(f"Script directory        : {SCRIPT_DIR}")
    print(f"Config file             : {CONFIG_FILE}")
    print(f"Selection mode          : {selection_mode}")
    print(f"Processed-data root     : {processed_data_root}")
    print(f"Downsampling factor     : {ds_factor} [Z, Y, X]")
    print(f"Original voxel size     : {voxel_size} µm [Z, Y, X]")
    print(f"Foreground label        : {FG_LABEL} (fixed)")
    print(
        "Output directory       : "
        + (
            str(args.output_dir.expanduser().resolve())
            if args.output_dir is not None
            else "default derived from each input folder"
        )
    )

    if args.folder is not None:
        print(
            "Processed-data root use: ignored because --folder was supplied"
        )

    print("-" * 72)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        ds_factor = positive_int_triplet(
            args.ds_factor,
            "--ds-factor",
        )
        voxel_size = positive_float_triplet(
            args.voxel_size,
            "--voxel-size",
        )
    except ValueError as exc:
        parser.error(str(exc))

    processed_data_root = (
        args.processed_data_root.expanduser().resolve()
    )

    print_configuration(
        args=args,
        processed_data_root=processed_data_root,
        ds_factor=ds_factor,
        voxel_size=voxel_size,
    )

    if args.list:
        folders = find_all_saf_outputs(processed_data_root)

        if not folders:
            print("No SAF output folders were found.")
            return

        print(f"\nAvailable SAF output folders ({len(folders)} found):")

        for folder in folders:
            n_files = len(find_segmentation_files(folder))
            print(f"  {folder} ({n_files} matching segmentation files)")

        return

    if args.folder is not None:
        folders = [args.folder.expanduser().resolve()]

    elif args.strain is not None:
        folders = find_strain_saf_outputs(
            strain=args.strain,
            processed_data_root=processed_data_root,
        )

    else:
        folders = find_all_saf_outputs(processed_data_root)

    if not folders:
        print("No SAF output folders matched the selected mode.")
        sys.exit(1)

    print(f"\nNumber of SAF folders selected: {len(folders)}")

    successes = 0
    failures = 0
    multiple_inputs = len(folders) > 1

    for folder in folders:
        successful = process_folder(
            segmentation_dir=folder,
            ds_factor=ds_factor,
            voxel_size=voxel_size,
            fg_label=FG_LABEL,
            requested_output_dir=args.output_dir,
            multiple_inputs=multiple_inputs,
        )

        if successful:
            successes += 1
        else:
            failures += 1

    print(f"\n{'=' * 72}")
    print("Processing summary")
    print(f"Successful folders: {successes}")
    print(f"Failed folders    : {failures}")
    print(f"{'=' * 72}")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
