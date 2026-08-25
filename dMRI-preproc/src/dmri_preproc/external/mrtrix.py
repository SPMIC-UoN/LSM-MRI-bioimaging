"""MRtrix3 command builders - see external/fsl.py for the pattern. Requires
MRtrix3 installed separately (https://www.mrtrix.org) and on $PATH.
"""

from __future__ import annotations

from pathlib import Path


def mrdegibbs(in_file: str | Path, out_file: str | Path, force: bool = True) -> list[str]:
    argv = ["deGibbs3D", str(in_file), str(out_file)]
    if force:
        argv.append("-force")
    return argv


def dwidenoise(
    in_file: str | Path,
    out_file: str | Path,
    mask: str | Path | None = None,
    noise_map: str | Path | None = None,
    force: bool = True,
) -> list[str]:
    argv = ["dwidenoise", str(in_file), str(out_file)]
    if mask is not None:
        argv += ["-mask", str(mask)]
    if noise_map is not None:
        argv += ["-noise", str(noise_map)]
    if force:
        argv.append("-force")
    return argv
