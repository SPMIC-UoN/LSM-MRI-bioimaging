#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path

from helper_functions_convert_tiff2nifty_fix import (
    find_raw_datasets,
    process_dataset,
)


VOXEL_SIZE = (4.0, 0.98, 0.98)


def main():
    parser = argparse.ArgumentParser(
        description="Convert OME-TIFF files to H5 and downsampled TIFF/NIfTI previews."
    )

    parser.add_argument(
        "--main_dir",
        type=str,
        required=True,
        help="Base directory containing strain directories.",
    )

    parser.add_argument(
        "--out_dir",
        type=str,
        required=True,
        help="Output directory.",
    )

    parser.add_argument(
        "--strains",
        nargs="*",
        default=None,
        help="Optional list of strains. If omitted, all subdirectories under main_dir are used.",
    )

    parser.add_argument(
        "--channel",
        type=int,
        nargs="+",
        default=[0, 1],
        help="Channel(s) to transform. Options: 0, 1, or 0 1. Default: 0 1.",
    )

    parser.add_argument(
        "--ds_factor",
        type=int,
        nargs=3,
        required=True,
        help="Downsampling factor as three integers: z y x. Example: 8 32 32.",
    )

    parser.add_argument(
        "--mag",
        type=str,
        default="4xobj_1p66xzoom_4um_step",
        help="Magnification directory name.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing outputs.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan only; do not write outputs.",
    )

    parser.add_argument(
        "--keep_h5",
        action="store_true",
        help="Keep intermediate H5 files. Default is to delete them after previews are generated.",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    main_dir = Path(args.main_dir)
    out_dir = Path(args.out_dir)

    strains = args.strains or sorted(
        d.name for d in main_dir.iterdir()
        if d.is_dir()
    )

    if set(args.channel) == {0, 1}:
        logging.info("Transforming TIFF data for both channels.")
    else:
        logging.info("Transforming TIFF data for channel(s): %s", args.channel)

    datasets = find_raw_datasets(
        main_dir=main_dir,
        magnification=args.mag,
        strains=strains,
        channels=args.channel,
    )

    if len(datasets) == 0:
        raise RuntimeError("No matching raw TIFF datasets found.")

    logging.info("Found %d dataset(s):", len(datasets))

    for d in datasets:
        logging.info(
            "%s | raw_folder=%s | session=%s | channel=C%02d | %s",
            d["strain"],
            d["raw_folder"] or ".",
            d["session"],
            d["channel"],
            d["path"],
        )

    for d in datasets:
        process_dataset(
            dataset=d,
            out_main=out_dir,
            voxel=VOXEL_SIZE,
            ds_factor=tuple(args.ds_factor),
            skip_existing=not args.force,
            dry_run=args.dry_run,
            keep_h5=args.keep_h5,
        )


if __name__ == "__main__":
    main()
