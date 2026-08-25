"""Brain mask creation. Mean b0 is computed directly (pure numpy/nibabel);
skull-stripping uses FSL's `bet4animal`.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import nibabel as nib
import numpy as np

from .external import fsl
from .external.run import run


def mean_b0_image(dwi_path: str | Path, bvals: np.ndarray, b0_threshold: float = 50.0):
    img = cast(nib.Nifti1Image, nib.load(str(dwi_path)))
    data = img.get_fdata()
    bvals = np.asarray(bvals)
    b0_mask = bvals < b0_threshold
    if not np.any(b0_mask):
        raise ValueError(f"no b0 volumes found (bval < {b0_threshold})")
    mean = data[..., b0_mask].mean(axis=-1)
    return nib.Nifti1Image(mean.astype(np.float32), img.affine, img.header)


def create_brain_mask(
    dwi_path: str | Path,
    bvals: np.ndarray,
    out_mask_path: str | Path,
    tmp_dir: str | Path,
    f: float = 0.075,
    z: int = 6,
    log_dir: str | Path | None = None,
) -> Path:
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    b0_mean_path = tmp_dir / "b0_mean.nii.gz"
    nib.save(mean_b0_image(dwi_path, bvals), b0_mean_path)

    bet_prefix = tmp_dir / "nodif_brain"
    run(fsl.bet4animal(b0_mean_path, bet_prefix, f=f, z=z), "bet4animal", log_dir)

    out_mask_path = Path(out_mask_path)
    produced_mask = Path(f"{bet_prefix}_mask.nii.gz")
    produced_mask.replace(out_mask_path)
    return out_mask_path
