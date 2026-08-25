"""Gibbs de-ringing (MRtrix) -> TOPUP -> EDDY (FSL)."""

from __future__ import annotations

from pathlib import Path

from .external import fsl, mrtrix
from .external.run import run


def write_index_file(path: str | Path, n_volumes: int) -> None:
    """All volumes assumed to share the same phase-encoding."""
    Path(path).write_text(" ".join(["1"] * n_volumes) + "\n")


def write_acqp_file(
    path: str | Path, phase_encode_axis: tuple[int, int, int], readout_time_ms: float
) -> None:
    """EDDY's acqp file - one row, since all volumes here share the same
    phase-encoding (see write_index_file)."""
    x, y, z = phase_encode_axis
    Path(path).write_text(f"{x} {y} {z} {readout_time_ms}\n")


def write_topup_acqp_file(
    path: str | Path, phase_encode_axis: tuple[int, int, int], readout_time_ms: float
) -> None:
    """TOPUP's acqp file - two rows (blip-up then blip-down: the phase-
    encode axis and its negation), one per volume in the b0 pair TOPUP
    estimates the field from."""
    x, y, z = phase_encode_axis
    Path(path).write_text(f"{x} {y} {z} {readout_time_ms}\n{-x} {-y} {-z} {readout_time_ms}\n")


def run_gibbs(in_file: str | Path, out_file: str | Path, log_dir: str | Path | None = None) -> None:
    run(mrtrix.mrdegibbs(in_file, out_file), "gibbs", log_dir)


def run_topup(
    b0_pair_file: str | Path,
    acqp_file: str | Path,
    config_file: str | Path,
    out_prefix: str | Path,
    field_file: str | Path,
    unwarped_file: str | Path,
    log_file: str | Path,
    log_dir: str | Path | None = None,
) -> None:
    run(
        fsl.topup(
            imain=b0_pair_file,
            datain=acqp_file,
            config=config_file,
            out=out_prefix,
            fout=field_file,
            iout=unwarped_file,
            logout=log_file,
        ),
        "topup",
        log_dir,
    )


def run_eddy(
    dwi_file: str | Path,
    mask_file: str | Path,
    acqp_file: str | Path,
    index_file: str | Path,
    bvecs_file: str | Path,
    bvals_file: str | Path,
    topup_prefix: str | Path,
    out_prefix: str | Path,
    log_dir: str | Path | None = None,
) -> None:
    run(
        fsl.eddy(
            imain=dwi_file,
            mask=mask_file,
            acqp=acqp_file,
            index=index_file,
            bvecs=bvecs_file,
            bvals=bvals_file,
            topup_out=topup_prefix,
            out=out_prefix,
        ),
        "eddy",
        log_dir,
    )
