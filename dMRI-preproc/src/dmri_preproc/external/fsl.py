"""FSL command builders - pure functions returning argv lists, executed via
external/run.py. Requires FSL installed separately (https://fsl.fmrib.ox.ac.uk)
and on $PATH.
"""

from __future__ import annotations

from pathlib import Path


def bet4animal(
    in_file: str | Path, out_prefix: str | Path, f: float = 0.075, z: int = 6
) -> list[str]:
    return ["bet4animal", str(in_file), str(out_prefix), "-m", "-z", str(z), "-f", str(f)]


def topup(
    imain: str | Path,
    datain: str | Path,
    config: str | Path,
    out: str | Path,
    fout: str | Path,
    iout: str | Path,
    logout: str | Path,
) -> list[str]:
    return [
        "topup",
        f"--imain={imain}",
        f"--datain={datain}",
        f"--config={config}",
        f"--out={out}",
        f"--fout={fout}",
        f"--iout={iout}",
        f"--logout={logout}",
        "--verbose",
    ]


def eddy(
    imain: str | Path,
    mask: str | Path,
    acqp: str | Path,
    index: str | Path,
    bvecs: str | Path,
    bvals: str | Path,
    topup_out: str | Path,
    out: str | Path,
) -> list[str]:
    return [
        "eddy",
        f"--imain={imain}",
        f"--mask={mask}",
        f"--acqp={acqp}",
        f"--index={index}",
        f"--bvecs={bvecs}",
        f"--bvals={bvals}",
        f"--topup={topup_out}",
        f"--out={out}",
        "--cnr_maps",
        "--data_is_shelled",
        "--verbose",
        "--residuals",
    ]


def eddy_quad(
    eddy_prefix: str | Path,
    index: str | Path,
    acqp: str | Path,
    mask: str | Path,
    bvals: str | Path,
    bvecs: str | Path,
    field: str | Path,
    out: str | Path,
) -> list[str]:
    return [
        "eddy_quad",
        str(eddy_prefix),
        "-idx",
        str(index),
        "-par",
        str(acqp),
        "-m",
        str(mask),
        "-b",
        str(bvals),
        "-g",
        str(bvecs),
        "-f",
        str(field),
        "-o",
        str(out),
    ]


def select_dwi_vols(
    in_file: str | Path,
    bvals: str | Path,
    out_file: str | Path,
    b0_placeholder: int,
    bvalues: list[float],
    obv: str | Path | None = None,
) -> list[str]:
    argv = ["select_dwi_vols", str(in_file), str(bvals), str(out_file), str(b0_placeholder)]
    for b in bvalues:
        argv += ["-b", str(b)]
    if obv is not None:
        argv += ["-obv", str(obv)]
    return argv


def dtifit(
    in_file: str | Path,
    mask: str | Path,
    bvals: str | Path,
    bvecs: str | Path,
    out_prefix: str | Path,
    kurt: bool = False,
    save_tensor: bool = False,
) -> list[str]:
    argv = [
        "dtifit",
        "-k",
        str(in_file),
        "-m",
        str(mask),
        "-b",
        str(bvals),
        "-r",
        str(bvecs),
        "-o",
        str(out_prefix),
    ]
    if kurt:
        argv.append("--kurt")
    if save_tensor:
        argv.append("--save_tensor")
    return argv


def fslcpgeom(in_file: str | Path, out_file: str | Path) -> list[str]:
    """Copies the NIfTI geometry (affine/qform/sform) from `in_file` onto
    `out_file` in place - needed after NORDIC, whose own NIfTI writer
    doesn't preserve the input header."""
    return ["fslcpgeom", str(in_file), str(out_file)]
