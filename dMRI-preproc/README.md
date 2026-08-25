# dMRI-preproc

Preprocessing and biophysical modelling code for the ex-vivo mouse-brain
dMRI paper: intensity normalisation, NORDIC denoising, brain masking,
Gibbs de-ringing, susceptibility/eddy-current correction (TOPUP/EDDY), and DKI/SANDI model fitting.

This is a standalone extract of the relevant part of the lab's larger
pipeline, built specifically so the preprocessing behind this paper can be
re-run independently of that internal codebase.

## External dependencies

You need, on `$PATH`:

- **FSL** (https://fsl.fmrib.ox.ac.uk) - `bet4animal`, `topup`, `eddy`,
  `eddy_quad`, `select_dwi_vols`, `dtifit`, `fslcpgeom`. Andersson et al.,
  2003 (TOPUP); Andersson and Sotiropoulos, 2016 (EDDY).
- **MRtrix3** (https://www.mrtrix.org) - `deGibbs3D`, `dwidenoise`.
  Tournier et al., 2019.
- **SANDI-Matlab-Toolbox**
  (https://github.com/palombom/SANDI-Matlab-Toolbox-Latest-Release) -
  clone it and pass its directory as `--toolbox-dir`. Palombo et al., 2020.

## Install

```bash
pip install -e .
```

## Inputs

One sample = five files:

| File | Description |
|---|---|
| `--mag` | 4D magnitude NIfTI, whole multi-shell acquisition, volumes in acquisition order |
| `--phase` | 4D phase NIfTI, same volume order as `--mag` |
| `--bval` | FSL-format bval for `--mag`/`--phase` |
| `--bvec` | FSL-format bvec for `--mag`/`--phase` |
| `--pa-b0` | A single blip-reversed (PA) b0 magnitude volume, for TOPUP |

Each shell is expected to lead with its own b0 volume(s) - normalisation
detects shell boundaries directly from `--bval`.

## Usage

```bash
dmri-preproc preprocess \
    --mag mag_merged.nii.gz \
    --phase phase_merged.nii.gz \
    --bval merged.bval \
    --bvec merged.bvec \
    --pa-b0 b0_blipDown.nii.gz \
    --out-dir out/ \
    --nordic-code-dir /path/to/NORDIC_Raw

dmri-preproc model-dki \
    --data out/dwi_preproc.nii.gz \
    --mask out/brain_mask.nii.gz \
    --out-prefix out/dki/dki \
    --work-dir out/dki/tmp

dmri-preproc model-sandi \
    --data out/dwi_preproc.nii.gz \
    --mask out/brain_mask.nii.gz \
    --out-dir out/sandi \
    --toolbox-dir /path/to/SANDI-Matlab-Toolbox-Latest-Release
```

Run `dmri-preproc <subcommand> --help` for the full flag list, including
overrides for the bet4animal threshold, phase-encode axis, readout time,
DKI b-value subset, and SANDI's Δ/δ/D0/fo-compartment settings (defaults match the paper).

## Outputs

```
out/
  dwi_preproc.nii.gz / .bval / .bvec   preprocessed magnitude DWI (post NORDIC/Gibbs/TOPUP/EDDY)
  brain_mask.nii.gz                     bet4animal whole-brain mask
  eddy_qc/                              eddy_quad output (per-shell SNR/CNR, motion, etc.)
  dki/                                  dki_FA.nii.gz, dki_MD.nii.gz, dki_kurt.nii.gz, ...
  sandi/                                 SANDI toolbox's own derivatives/ output structure
```

## Processing steps 

1. Intensity normalisation: each shell's mean b0 intensity is scaled to
   match a reference shell's (default: the first shell acquired).
2. NORDIC denoising, complex domain (normalised magnitude + phase).
3. Whole-brain mask: `bet4animal` on the denoised data's mean b0,
   `-f 0.075`.
4. Gibbs de-ringing (`deGibbs3D`) on the main data and on both the
   blip-up (first b0 of the main data) and blip-down (`--pa-b0`) images.
5. TOPUP on the Gibbs-corrected AP/PA b0 pair, then EDDY on the
   Gibbs-corrected main data using TOPUP's field.
6. DKI fit (`dtifit --kurt`) restricted to b = [1, 2.5, 5.5, 8.5] ms/μm².
7. SANDI fit (full 6-shell acquisition, b = [1, 2.5, 5.5, 8.5, 12.5, 17.5]
   ms/μm², fo/dot compartment included, fixed D0 = 2.0 μm²/ms).

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest
```
