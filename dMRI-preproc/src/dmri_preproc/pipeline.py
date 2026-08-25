"""Full preprocessing chain: normalise -> NORDIC denoise
-> mask -> Gibbs -> TOPUP -> EDDY 
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import cast

import nibabel as nib
import numpy as np

from . import distortion
from . import gradients as grad
from . import mask as mask_mod
from . import qc as qc_mod
from .denoise import run_nordic
from .normalise import normalise_merged

DEFAULT_TOPUP_CONFIG = Path(str(resources.files(__package__) / "resources" / "topup_mouse.cnf"))
DEFAULT_PHASE_ENCODE_AXIS = (1, 0, 0)
DEFAULT_READOUT_TIME_MS = 0.150


@dataclass
class PreprocessResult:
    mask_path: Path
    topup_field_path: Path
    qc_dir: Path
    final_dwi_path: Path  # + matching .bval / .bvec alongside it


def _extract_first_volume(in_path: str | Path, out_path: str | Path) -> None:
    img = cast(nib.Nifti1Image, nib.load(str(in_path)))
    first = np.asarray(img.dataobj[..., 0])
    nib.save(nib.Nifti1Image(first.astype(np.float32), img.affine, img.header), out_path)


def _concat_volumes(in_paths: list[str | Path], out_path: str | Path) -> None:
    imgs = [cast(nib.Nifti1Image, nib.load(str(p))) for p in in_paths]
    data = np.stack([np.squeeze(np.asarray(img.dataobj)) for img in imgs], axis=-1)
    nib.save(nib.Nifti1Image(data.astype(np.float32), imgs[0].affine, imgs[0].header), out_path)


def _strip_nii_gz(path: Path) -> str:
    s = str(path)
    return s[: -len(".nii.gz")] if s.endswith(".nii.gz") else str(path.with_suffix(""))


def preprocess(
    mag_path: str | Path,
    phase_path: str | Path,
    bval_path: str | Path,
    bvec_path: str | Path,
    pa_b0_path: str | Path,
    out_dir: str | Path,
    nordic_code_dir: str | Path,
    reference_block_index: int = 0,
    bet_f: float = 0.075,
    bet_z: int = 6,
    phase_encode_axis: tuple[int, int, int] = DEFAULT_PHASE_ENCODE_AXIS,
    readout_time_ms: float = DEFAULT_READOUT_TIME_MS,
    topup_config_path: str | Path = DEFAULT_TOPUP_CONFIG,
) -> PreprocessResult:
    out_dir = Path(out_dir)
    work_dir = out_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    log_dir = out_dir / "logs"

    mag_img = cast(nib.Nifti1Image, nib.load(str(mag_path)))
    bvals = grad.read_fsl_bval(bval_path)
    bvecs = grad.read_fsl_bvec(bvec_path)

    # --- normalise (magnitude only - phase is merged but never normalised,
    # matching the paper's methods and the old pipeline this reproduces) ---
    normalised = normalise_merged(mag_img.get_fdata(), bvals, reference_block_index)
    normalised_path = work_dir / "mag_normalised.nii.gz"
    nib.save(nib.Nifti1Image(normalised.astype(np.float32), mag_img.affine), normalised_path)

    # --- NORDIC denoise ---
    denoised_path, _noisemap_path = run_nordic(
        normalised_path, phase_path, work_dir, "data_denoised", nordic_code_dir, log_dir=log_dir
    )

    # --- brain mask (from the denoised data's mean b0) ---
    mask_path = out_dir / "brain_mask.nii.gz"
    mask_mod.create_brain_mask(
        denoised_path, bvals, mask_path, work_dir, f=bet_f, z=bet_z, log_dir=log_dir
    )

    # --- Gibbs de-ringing: main data, blip-up (first vol of denoised data),
    # and the separately-provided blip-down (PA) b0, each corrected
    # individually before TOPUP ---
    gibbs_path = work_dir / "data_gibbs.nii.gz"
    distortion.run_gibbs(denoised_path, gibbs_path, log_dir)

    blip_up_path = work_dir / "b0_blipUp.nii.gz"
    _extract_first_volume(denoised_path, blip_up_path)
    blip_up_gibbs_path = work_dir / "b0_blipUp_gibbs.nii.gz"
    distortion.run_gibbs(blip_up_path, blip_up_gibbs_path, log_dir)

    blip_down_gibbs_path = work_dir / "b0_blipDown_gibbs.nii.gz"
    distortion.run_gibbs(pa_b0_path, blip_down_gibbs_path, log_dir)

    # --- TOPUP ---
    topup_dir = work_dir / "topup"
    topup_dir.mkdir(exist_ok=True)
    b0_pair_path = topup_dir / "b0_gibbs_topup.nii.gz"
    _concat_volumes([blip_up_gibbs_path, blip_down_gibbs_path], b0_pair_path)

    topup_acqp_path = topup_dir / "acqp.txt"
    distortion.write_topup_acqp_file(topup_acqp_path, phase_encode_axis, readout_time_ms)

    topup_out_prefix = topup_dir / "topup_output"
    field_path = topup_dir / "topup_field.nii.gz"
    unwarped_path = topup_dir / "topup_unwarped.nii.gz"
    topup_log_path = topup_dir / "topup.log"
    distortion.run_topup(
        b0_pair_path,
        topup_acqp_path,
        topup_config_path,
        topup_out_prefix,
        field_path,
        unwarped_path,
        topup_log_path,
        log_dir,
    )

    # --- EDDY ---
    eddy_dir = work_dir / "eddy"
    eddy_dir.mkdir(exist_ok=True)
    gibbs_img = cast(nib.Nifti1Image, nib.load(str(gibbs_path)))
    n_volumes = int(gibbs_img.shape[-1])
    index_path = eddy_dir / "index.txt"
    distortion.write_index_file(index_path, n_volumes)
    eddy_acqp_path = eddy_dir / "acqp.txt"
    distortion.write_acqp_file(eddy_acqp_path, phase_encode_axis, readout_time_ms)

    eddy_bvals_path = eddy_dir / "bvals"
    eddy_bvecs_path = eddy_dir / "bvecs"
    grad.write_fsl_bval(eddy_bvals_path, bvals)
    grad.write_fsl_bvec(eddy_bvecs_path, bvecs)

    eddy_out_prefix = eddy_dir / "data_eddy_corrected"
    distortion.run_eddy(
        gibbs_path,
        mask_path,
        eddy_acqp_path,
        index_path,
        eddy_bvecs_path,
        eddy_bvals_path,
        topup_out_prefix,
        eddy_out_prefix,
        log_dir,
    )

    rotated_bvecs_path = Path(f"{eddy_out_prefix}.eddy_rotated_bvecs")
    fixed_bvecs = grad.fix_nan_bvecs(grad.read_fsl_bvec(rotated_bvecs_path))
    grad.write_fsl_bvec(rotated_bvecs_path, fixed_bvecs)

    # --- eddy QC ---
    qc_dir = out_dir / "eddy_qc"
    qc_mod.run_eddy_quad(
        eddy_out_prefix,
        index_path,
        eddy_acqp_path,
        mask_path,
        eddy_bvals_path,
        rotated_bvecs_path,
        field_path,
        qc_dir,
        log_dir,
    )

    # --- copy EDDY's output into the canonical output path ---
    final_dwi_path = out_dir / "dwi_preproc.nii.gz"
    shutil.copy2(f"{eddy_out_prefix}.nii.gz", final_dwi_path)
    final_base = _strip_nii_gz(final_dwi_path)
    shutil.copy2(eddy_bvals_path, f"{final_base}.bval")
    shutil.copy2(rotated_bvecs_path, f"{final_base}.bvec")

    return PreprocessResult(
        mask_path=mask_path,
        topup_field_path=field_path,
        qc_dir=qc_dir,
        final_dwi_path=final_dwi_path,
    )
