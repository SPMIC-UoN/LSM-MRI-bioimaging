"""Diffusion kurtosis imaging (Jensen et al., 2005) via FSL's dtifit.

Fitted to the b = [1, 2.5, 5.5, 8.5] ms/um^2 shells only.
"""

from __future__ import annotations

from pathlib import Path

from .external import fsl
from .external.run import run

DKI_SHELLS: list[float] = [1000, 2500, 5500, 8500]


def select_shells(
    data: str | Path,
    bvals: str | Path,
    bvecs: str | Path,
    out_path: str | Path,
    shells: list[float],
    log_dir: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    """Extracts b0 + the given non-zero b-value shells via FSL's
    select_dwi_vols. Writes sidecars by appending .bval/.bvec onto the
    full out_path (including the .nii.gz suffix)."""
    cmd = fsl.select_dwi_vols(data, bvals, out_path, 0, shells, obv=bvecs)
    run(cmd, "select_dwi_vols", log_dir)
    return Path(out_path), Path(f"{out_path}.bval"), Path(f"{out_path}.bvec")


def fit_dki(
    data: str | Path,
    mask: str | Path,
    bvals: str | Path,
    bvecs: str | Path,
    out_prefix: str | Path,
    log_dir: str | Path | None = None,
) -> Path:
    """DKI fit (--kurt --save_tensor). Caller selects the b-value subset
    first (see prepare_and_fit_dki)."""
    run(
        fsl.dtifit(data, mask, bvals, bvecs, out_prefix, kurt=True, save_tensor=True),
        "dtifit_dki",
        log_dir,
    )
    # dtifit --kurt writes the kurtosis parameter volume as
    # "<prefix>_kurt.nii.gz", not "_MK.nii.gz".
    return Path(f"{out_prefix}_kurt.nii.gz")


def prepare_and_fit_dki(
    data: str | Path,
    mask: str | Path,
    bvals: str | Path,
    bvecs: str | Path,
    work_dir: str | Path,
    out_prefix: str | Path,
    log_dir: str | Path | None = None,
) -> Path:
    """select_dwi_vols (b=1000,2500,5500,8500) -> fit_dki."""
    subset_path = Path(work_dir) / "data_b1k_b2p5k_b5p5k_b8p5k.nii.gz"
    sel_data, sel_bvals, sel_bvecs = select_shells(
        data, bvals, bvecs, subset_path, DKI_SHELLS, log_dir
    )
    return fit_dki(sel_data, mask, sel_bvals, sel_bvecs, out_prefix, log_dir)
