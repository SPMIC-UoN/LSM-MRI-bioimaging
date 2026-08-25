"""Complex-domain denoising via NORDIC (Moeller et al., 2021).

Requires NORDIC (https://github.com/SteenMoeller/NORDIC_Raw) and MATLAB
installed separately; `nordic_code_dir` should point at the directory
containing NORDIC's `NIFTI_NORDIC.m`.
"""

from __future__ import annotations

from pathlib import Path

from .external import fsl
from .external.matlab import add_path, matlab_command
from .external.run import run


def run_nordic(
    magnitude: str | Path,
    phase: str | Path,
    out_dir: str | Path,
    out_name: str,
    nordic_code_dir: str | Path,
    log_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Runs NORDIC on (magnitude, phase) -> (denoised, noise_map) under
    `out_dir/{out_name}[.nii.gz|_noisemap.nii.gz]`. Returns
    (denoised_path, noisemap_path) - the noisemap is only guaranteed to
    exist if NORDIC's `ARG.save_add_info` produced one."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    arg_struct = (
        "ARG = struct(); "
        "ARG.temporal_phase = 3; "
        "ARG.phase_filter_width = 3; "
        "ARG.save_add_info = 1; "
        "ARG.write_gzipped_niftis = 1; "
        f"ARG.DIROUT = '{out_dir}/'"
    )
    call = f"NIFTI_NORDIC('{magnitude}', '{phase}', '{out_name}', ARG)"
    cmd = matlab_command(call, statements_before=[add_path(str(nordic_code_dir)), arg_struct])
    run(cmd, "nordic_denoise", log_dir)

    denoised_path = out_dir / f"{out_name}.nii.gz"
    noisemap_path = out_dir / f"{out_name}_noisemap.nii.gz"

    for out_path in (denoised_path, noisemap_path):
        if out_path.is_file():
            run(fsl.fslcpgeom(magnitude, out_path), "fslcpgeom", log_dir)

    if not denoised_path.is_file():
        raise RuntimeError(f"NORDIC did not produce the expected output {denoised_path}")

    return denoised_path, noisemap_path
