"""Eddy QC (`eddy_quad`) wrapper."""

from __future__ import annotations

from pathlib import Path

from .external import fsl
from .external.run import run


def run_eddy_quad(
    eddy_prefix: str | Path,
    index_file: str | Path,
    acqp_file: str | Path,
    mask_file: str | Path,
    bvals_file: str | Path,
    rotated_bvecs_file: str | Path,
    field_file: str | Path,
    out_dir: str | Path,
    log_dir: str | Path | None = None,
) -> None:
    # eddy_quad creates its own output directory and refuses to run if it
    # already exists - remove only an empty pre-existing directory (never
    # a non-empty one, which would mean real prior QC output).
    out_dir = Path(out_dir)
    if out_dir.is_dir() and not any(out_dir.iterdir()):
        out_dir.rmdir()

    run(
        fsl.eddy_quad(
            eddy_prefix=eddy_prefix,
            index=index_file,
            acqp=acqp_file,
            mask=mask_file,
            bvals=bvals_file,
            bvecs=rotated_bvecs_file,
            field=field_file,
            out=out_dir,
        ),
        "eddy_quad",
        log_dir,
    )
