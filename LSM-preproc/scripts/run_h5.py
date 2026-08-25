#!/usr/bin/env python3

import argparse
import logging
from pathlib import Path
import re
import os

from run_ilastik import process_ilastik
from run_cellpose import process_cellpose

VOXEL_SIZE = (4.0, 0.98, 0.98)


# Mapping: animal_id -> magnification -> (GFAP_channel, NeuN_channel)
CHANNEL_MAP = {
    # GFAP=C00, NeuN=C01 (both 1x and 4x)
    "BXTA_1p3a": {"1x": (0, 1), "4x": (0, 1)},
    "BXTB_1p1e": {"1x": (0, 1), "4x": (0, 1)},
    "BXTC_1p2a": {"1x": (0, 1), "4x": (0, 1)},
    "BXTD_1p1a": {"1x": (0, 1), "4x": (0, 1)},
    "BXTF_1p2b": {"1x": (0, 1), "4x": (0, 1)},
    "BXTT_1p1b": {"1x": (0, 1), "4x": (0, 1)},
    "BXTT_1p2a": {"1x": (0, 1), "4x": (0, 1)},
    "TAGL_2p1b": {"1x": (0, 1), "4x": (0, 1)},

    # 1x: GFAP=C02, NeuN=C01
    # 4x: GFAP=C01, NeuN=C00
    "BXTF_1p2d": {"1x": (2, 1), "4x": (1, 0)},
    "TAGL_2p4e": {"1x": (2, 1), "4x": (1, 0)},

    # 1x: GFAP=C02, NeuN=C01
    # 4x: GFAP=C00, NeuN=C01
    "BXTH_1p1c": {"1x": (2, 1), "4x": (0, 1)},
}

def get_channels(filename):
    """
    Returns (gfap_channel, neun_channel) from a filename.

    Example filenames:
        BXT_1p3a_1xobj.nd2
        BXT_1p2d_4xobj.czi
        TAG_2p4e-1x.tif
    """
    #name = os.path.splitext(os.path.basename(filename))[0]
    name = filename

    # Find the animal ID
    animal = None
    for aid in CHANNEL_MAP:
        if aid.lower() in name.lower():
            animal = aid
            break
    if animal is None:
        raise ValueError(f"Unknown animal ID in '{filename}'")

    # Determine magnification
    lower = name.lower()
    if re.search(r'1xobj', lower):
        mag = "1x"
    elif re.search(r'4xobj', lower):
        mag = "4x"
    else:
        print("WARNING: could not find mag assuming 4x")
        mag = "4x"

    return CHANNEL_MAP[animal][mag]

def main():
    parser = argparse.ArgumentParser(
        description="Convert OME-TIFF files to H5 and downsampled TIFF/NIfTI previews."
    )

    parser.add_argument(
        "--h5",
        type=str,
        required=True,
        help="H5 filename",
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

    h5_path = Path(args.h5)
    channel = int(h5_path.stem.split("_")[-1][1:])  # Extract channel from filename
    logging.info(f"Processing H5 file: {h5_path}, channel: {channel}")

    gfap_channel, neun_channel = get_channels(str(h5_path))
    logging.info(f"GFAP channel: {gfap_channel}, NeuN channel: {neun_channel}")
    if channel == gfap_channel:
        logging.info("Running Ilastik processing for GFAP channel.")
        process_ilastik(
            h5_path,
            slice_range=int(os.environ.get("SLURM_ARRAY_TASK_ID", 0)) if os.environ.get("SLURM_ARRAY_TASK_ID") is not None else None,
            skip_existing=True,
            dry_run=False,
            n_processes=100 # FIXME hardcoded
        )
    if channel == neun_channel:
        logging.info("Running Cellpose processing for NeuN channel.")
        process_cellpose(
            h5_path,
            array_idx=int(os.environ.get("SLURM_ARRAY_TASK_ID", 0)) if os.environ.get("SLURM_ARRAY_TASK_ID") is not None else None,
            n_array=100, # FIXME hardcoded
            n_workers=10
        )


if __name__ == "__main__":
    main()
