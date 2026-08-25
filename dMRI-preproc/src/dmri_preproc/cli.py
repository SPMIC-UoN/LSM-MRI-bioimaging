"""Single entry point (`dmri-preproc` console script).

    dmri-preproc preprocess ...
    dmri-preproc model-dki ...
    dmri-preproc model-sandi ...

Run `dmri-preproc <subcommand> --help` for the full flag list.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import dki as dki_mod
from . import sandi as sandi_mod
from .pipeline import (
    DEFAULT_PHASE_ENCODE_AXIS,
    DEFAULT_READOUT_TIME_MS,
    DEFAULT_TOPUP_CONFIG,
    preprocess,
)

app = typer.Typer(add_completion=False)


def _strip_nii_gz(path: Path) -> str:
    s = str(path)
    return s[: -len(".nii.gz")] if s.endswith(".nii.gz") else str(path.with_suffix(""))


@app.command(name="preprocess")
def preprocess_cmd(
    mag: Path = typer.Option(..., help="Merged 4D magnitude NIfTI (whole acquisition)"),
    phase: Path = typer.Option(..., help="Merged 4D phase NIfTI (same volume order as --mag)"),
    bval: Path = typer.Option(..., help="FSL-format bval sidecar for --mag/--phase"),
    bvec: Path = typer.Option(..., help="FSL-format bvec sidecar for --mag/--phase"),
    pa_b0: Path = typer.Option(..., help="Blip-reversed (PA) b0 magnitude NIfTI, for TOPUP"),
    out_dir: Path = typer.Option(..., help="Output directory"),
    nordic_code_dir: Path = typer.Option(
        ..., help="Directory containing NORDIC's NIFTI_NORDIC.m (from NORDIC_Raw)"
    ),
    bet_f: float = typer.Option(0.075, help="bet4animal fractional intensity threshold"),
    bet_z: int = typer.Option(6, help="bet4animal -z (slice-wise search extent)"),
    phase_encode_x: int = typer.Option(DEFAULT_PHASE_ENCODE_AXIS[0]),
    phase_encode_y: int = typer.Option(DEFAULT_PHASE_ENCODE_AXIS[1]),
    phase_encode_z: int = typer.Option(DEFAULT_PHASE_ENCODE_AXIS[2]),
    readout_time_ms: float = typer.Option(
        DEFAULT_READOUT_TIME_MS, help="TOPUP/EDDY total readout time"
    ),
    topup_config: Path = typer.Option(DEFAULT_TOPUP_CONFIG, help="TOPUP --config file"),
) -> None:
    """normalise -> NORDIC denoise -> mask -> Gibbs -> TOPUP -> EDDY -> eddy_quad."""
    result = preprocess(
        mag_path=mag,
        phase_path=phase,
        bval_path=bval,
        bvec_path=bvec,
        pa_b0_path=pa_b0,
        out_dir=out_dir,
        nordic_code_dir=nordic_code_dir,
        bet_f=bet_f,
        bet_z=bet_z,
        phase_encode_axis=(phase_encode_x, phase_encode_y, phase_encode_z),
        readout_time_ms=readout_time_ms,
        topup_config_path=topup_config,
    )
    typer.echo(f"preprocessed data: {result.final_dwi_path}")
    typer.echo(f"brain mask: {result.mask_path}")
    typer.echo(f"eddy QC: {result.qc_dir}")


@app.command()
def model_dki(
    data: Path = typer.Option(..., help="Preprocessed 4D DWI NIfTI (e.g. dwi_preproc.nii.gz)"),
    mask: Path = typer.Option(...),
    out_prefix: Path = typer.Option(..., help="Output prefix, e.g. out_dir/dki/dki"),
    work_dir: Path = typer.Option(
        ..., help="Scratch directory for the b-value-subset intermediate"
    ),
) -> None:
    """DKI fit (Jensen et al., 2005), restricted to b = [1, 2.5, 5.5, 8.5] ms/um^2."""
    base = _strip_nii_gz(data)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    kurt_path = dki_mod.prepare_and_fit_dki(
        data, mask, f"{base}.bval", f"{base}.bvec", work_dir, out_prefix
    )
    typer.echo(f"DKI kurtosis map: {kurt_path}")


@app.command()
def model_sandi(
    data: Path = typer.Option(..., help="Preprocessed 4D DWI NIfTI (e.g. dwi_preproc.nii.gz)"),
    mask: Path = typer.Option(...),
    out_dir: Path = typer.Option(..., help="SANDI output directory"),
    toolbox_dir: Path = typer.Option(..., help="Path to SANDI-Matlab-Toolbox-Latest-Release"),
    delta: float = typer.Option(20.0, help="Diffusion time (Delta), ms"),
    small_delta: float = typer.Option(7.5, help="Gradient pulse duration (delta), ms"),
    with_dot: bool = typer.Option(True, help="Include the fo (dot) compartment"),
    dsoma: float = typer.Option(
        sandi_mod.DEFAULT_DSOMA_UM2_MS, help="Fixed D0 diffusivity, um^2/ms"
    ),
) -> None:
    """SANDI fit (Palombo et al., 2020) using the full multi-shell acquisition."""
    base = _strip_nii_gz(data)
    sandi_mod.prepare_and_fit_sandi(
        data,
        f"{base}.bval",
        f"{base}.bvec",
        mask,
        out_dir,
        delta,
        small_delta,
        toolbox_dir,
        with_dot,
        dsoma,
    )
    typer.echo(f"SANDI output: {out_dir}")


if __name__ == "__main__":
    app()
