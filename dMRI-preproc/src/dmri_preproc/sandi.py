"""SANDI (Palombo et al., 2020) fitting via the SANDI-Matlab-Toolbox
(https://github.com/palombom/SANDI-Matlab-Toolbox-Latest-Release, installed
separately). Fitted using the full acquisition (b = [1, 2.5, 5.5,
8.5, 12.5, 17.5] ms/um^2) with an fo (dot) compartment and a fixed D0 of
2.0 um^2/ms.

Calls `matlab/dmri_preproc_sandi_batch_analysis.m` - a small modified
copy of the toolbox's own `SANDI_batch_analysis.m` rather than the
unmodified upstream function, because the upstream one hardcodes
WithDot=0/Dsoma=3 inside `InitializeSANDIinput.m`. Lives under `matlab/`,
not `resources/` - MATLAB refuses to `addpath` any folder literally named
`resources` (a reserved name, like `private`/`@class`), which silently
left this function undefined on the path until moved.
"""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from .external import mrtrix
from .external.matlab import add_path, add_path_recursive, matlab_command
from .external.run import run

DEFAULT_DSOMA_UM2_MS = 2.0
_MATLAB_DIR = Path(str(resources.files(__package__) / "matlab"))


def prepare_sandi_data(
    data: str | Path,
    bvals: str | Path,
    bvecs: str | Path,
    mask: str | Path,
    sandi_dir: str | Path,
    sub: str = "01",
    ses: str = "01",
    log_dir: str | Path | None = None,
) -> Path:
    """Copies DWI/bval/bvec/mask into the folder layout
    `dmri_preproc_sandi_batch_analysis`/`SANDI_batch_analysis` expects,
    then runs `dwidenoise` (MPPCA) to produce the noisemap SANDI uses to
    estimate the Rician noise floor. Returns the created sub/ses
    directory."""
    prep_dir = Path(sandi_dir) / "derivatives" / "preprocessed" / f"sub-{sub}" / f"ses-{ses}"
    prep_dir.mkdir(parents=True, exist_ok=True)
    basename = f"sub-{sub}_ses-{ses}_acq-01_run-01_desc-preproc"

    dwi_out = prep_dir / f"{basename}_dwi.nii.gz"
    mask_out = prep_dir / f"{basename}_mask.nii.gz"
    shutil.copy2(data, dwi_out)
    shutil.copy2(bvals, prep_dir / f"{basename}_dwi.bval")
    shutil.copy2(bvecs, prep_dir / f"{basename}_dwi.bvec")
    shutil.copy2(mask, mask_out)

    denoised_out = prep_dir / f"{basename}_dwi_MPPCAdenoised.nii.gz"
    noisemap_out = prep_dir / f"{basename}_dwi_noisemap.nii.gz"
    run(
        mrtrix.dwidenoise(dwi_out, denoised_out, mask=mask_out, noise_map=noisemap_out),
        "dwidenoise_sandi_prep",
        log_dir,
    )
    return prep_dir


def fit_sandi(
    sandi_dir: str | Path,
    delta_ms: float,
    small_delta_ms: float,
    toolbox_dir: str | Path,
    with_dot: bool = True,
    dsoma_init: float = DEFAULT_DSOMA_UM2_MS,
    log_dir: str | Path | None = None,
) -> None:
    expr = (
        f"dmri_preproc_sandi_batch_analysis('{sandi_dir}', {delta_ms}, {small_delta_ms}, "
        f"[], {1 if with_dot else 0}, {dsoma_init})"
    )
    cmd = matlab_command(
        expr,
        statements_before=[
            add_path(str(_MATLAB_DIR)),
            add_path(str(toolbox_dir)),
            add_path_recursive(f"{toolbox_dir}/functions"),
        ],
    )
    run(cmd, "sandi_fit", log_dir)


def prepare_and_fit_sandi(
    data: str | Path,
    bvals: str | Path,
    bvecs: str | Path,
    mask: str | Path,
    sandi_dir: str | Path,
    delta_ms: float,
    small_delta_ms: float,
    toolbox_dir: str | Path,
    with_dot: bool = True,
    dsoma_init: float = DEFAULT_DSOMA_UM2_MS,
    log_dir: str | Path | None = None,
) -> None:
    """prepare_sandi_data -> fit_sandi."""
    prepare_sandi_data(data, bvals, bvecs, mask, sandi_dir, log_dir=log_dir)
    fit_sandi(sandi_dir, delta_ms, small_delta_ms, toolbox_dir, with_dot, dsoma_init, log_dir)
