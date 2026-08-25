# LSM–T2w MRI registration pipeline

**Author:** Stephania Assimopoulos  
**Original workflow documentation:** August 2026

This repository registers light-sheet microscopy (LSM) images and derived quantitative maps to ex vivo T2-weighted (T2w) MRI. It also applies the inverse transform for visualization in LSM space and provides scripts for quality-control figures and optional resampling.

The walkthrough below processes one subject, `TAGL_2p4e`, from input preparation through registration, visualization, and resampling.

## Workflow

| Step | Operation | Main output |
| --- | --- | --- |
| 1 | Prepare and preprocess the inputs | Thresholded, square-root-transformed NeuN registration image |
| 2 | Register LSM NeuN to T2w MRI | Forward LSM-to-T2w transform |
| 3 | Apply the forward and inverse transforms | Images and maps in both T2w and LSM spaces |
| 4 | Prepare split-view GIFs for quality control | Per-contrast visualization GIFs |
| 5A | Assemble one subject across orientations | Multi-orientation figure |
| 5B | Assemble subjects and contrasts | Single-orientation comparison figure |
| 6 | Optionally resample T2w-space LSM data | NIfTIs on a target-resolution grid |

## Requirements

- FSL 6.0.7.x, including `fslmaths` and `fslpython`
- Bash
- Python packages imported by the visualization scripts
- The scripts in this repository

At the original deployment site, the scripts were located at:

```text
/data/WT_bioimaging/WT_LSM_reg_pipeline/scripts
```

Update paths and environment configuration for your system.

## Run the pipeline: one-subject example

### Set the run configuration

```bash
module load fsl/6.0.7.x

project_dir=/data/WT_bioimaging/WT_082026_Paper_Codebase/LSM-MRI-reg
scripts_dir="${project_dir}/scripts"
base_dir="${project_dir}"
subject=TAGL_2p4e
data=data

subject_dir="${base_dir}/${subject}"
input_dir="${subject_dir}/${data}"
reg_name=4xobj_sqrt_to_t2w_direct_AllRegSteps_sqrt_thr250
```

All remaining commands assume these variables remain defined in the current shell.

### Step 1: Prepare the input data

Create the subject input directory:

```bash
mkdir -p "${input_dir}"
```

Copy or link the following files into it using these names:

| Input | Required filename |
| --- | --- |
| LSM NeuN channel | `4xobj_NeuN.nii.gz` |
| LSM GFAP channel | `4xobj_GFAP.nii.gz` |
| NeuN quantitative map | `NeuN_map.nii.gz` |
| GFAP quantitative map | `GFAP_map.nii.gz` |
| T2w MRI | `t2w.nii.gz` |
| T2w brain mask | `t2w_mask.nii.gz` |

> [!IMPORTANT]
> Confirm stain identity from the acquisition metadata. NeuN is often `C01` and GFAP often `C00` in this dataset, but channel numbering should not be assumed across acquisitions.

Create the NeuN image used to estimate the registration. Intensities below 250 are removed and the square root of the remaining intensities is taken:

```bash
fslmaths \
  "${input_dir}/4xobj_NeuN.nii.gz" \
  -thr 250 \
  -sqrt \
  "${input_dir}/4xobj_NeuN_thr250_sqrt.nii.gz"
```

Before continuing, visually inspect the processed NeuN image and confirm that all six required inputs have the expected orientation and spatial metadata.

### Step 2: Register LSM NeuN to T2w MRI

Run the volume-to-volume registration:

```bash
sh "${scripts_dir}/run_pipeline.sh" \
  "${scripts_dir}/volume_to_volume_template.yml" \
  "${subject}" \
  "${reg_name}" \
  "${base_dir}" \
  "${input_dir}/4xobj_NeuN_thr250_sqrt.nii.gz" \
  "" \
  "${input_dir}/t2w.nii.gz" \
  "${input_dir}/t2w_mask.nii.gz"
```

The empty argument (`""`) indicates that no source-image mask is supplied. The T2w mask is used only for the target image.

This step estimates the LSM-to-T2w registration using the thresholded, square-root-transformed NeuN image. Do not continue until the command finishes successfully and the registration outputs exist under the named registration directory.

### Step 3: Apply the transforms

Apply the completed registration to the images and quantitative maps:

```bash
sh "${scripts_dir}/apply_reg_loop.sh" \
  --script_dir "${scripts_dir}" \
  --base_dir "${base_dir}" \
  --subject "${subject}" \
  --reg_dir "${reg_name}"
```

By default, the script:

- searches `${base_dir}/${subject}/data` for input NIfTIs;
- applies the forward transform to place LSM images and maps in T2w space;
- applies the inverse transform to place T2w images in LSM space for visualization; and
- writes outputs beneath `${base_dir}/${subject}/t2w` and `${base_dir}/${subject}/4xobj`.

Alternative input directories, individual input files, and output directories can be supplied through the script's optional arguments.

Before making figures, inspect the transformed NeuN image against the T2w target and verify the inverse-transformed T2w image against the original LSM data.

### Step 4: Prepare visualization GIFs

Choose the output space and visualization settings. The example below prepares LSM-space (`4xobj`) views at a fractional slice position of `0.6`, using percentile-based intensity thresholds:

```bash
space=4xobj
slice=0.6
thresh_type=prc
mask_in_space="${subject_dir}/4xobj/t2w_to_4xobj_mask.nii.gz"

sh "${scripts_dir}/img_vis_prep_steps.sh" \
  --scripts_dir "${scripts_dir}" \
  --base_dir "${base_dir}" \
  --subject "${subject}" \
  --space "${space}" \
  --slice "${slice}" \
  --threshold "${thresh_type}" \
  --mask "${mask_in_space}"
```

Use `--overwrite` when existing visualization outputs should be regenerated.

The script prepares each contrast by:

1. scaling intensities using percentile or manual thresholds (`prc` or `man`);
2. splitting the images across the midline in the requested orientation;
3. stitching each contrast with the corresponding T2w view;
4. rescaling the stitched NIfTIs; and
5. overlaying the atlas boundary at the requested slice.

### Step 5A: Create a multi-orientation figure for one subject

Assemble axial, coronal, and sagittal views for each contrast:

```bash
figure_dir="${project_dir}/PNG_output"

fslpython "${scripts_dir}/make_gif_figure_flex.py" \
  --base_dir "${base_dir}" \
  --subject "${subject}" \
  --space "${space}" \
  --orientations ax cor sag \
  --split x x y \
  --out_dir "${figure_dir}" \
  --threshold "${thresh_type}" \
  --slice 0.5 0.5 0.6 \
  --orientation_scales ax=1.40 cor=1.00 sag=0.90 \
  --padding 20
```

Use `make_gif_figure.py` instead when the same slice should be displayed for all orientations:

```bash
fslpython "${scripts_dir}/make_gif_figure.py" \
  --base_dir "${base_dir}" \
  --subject "${subject}" \
  --space "${space}" \
  --orientations ax cor sag \
  --split x x y \
  --out_dir "${figure_dir}" \
  --threshold "${thresh_type}" \
  --slice 0.5 \
  --orientation_scales ax=1.40 cor=1.00 sag=0.90 \
  --padding 20
```

### Step 5B: Compare contrasts across one or more subjects

`subject_contrasts_single_orientation.py` creates one figure for a selected orientation, with rows representing subjects and columns representing contrasts.

For one subject in axial orientation:

```bash
fslpython "${scripts_dir}/subject_contrasts_single_orientation.py" \
  --base-dir "${base_dir}" \
  --space "${space}" \
  --subjects "${subject}" \
  --orientation ax \
  --split xsplit \
  --slice 0.5 \
  --threshold "${thresh_type}" \
  --output-dir "${figure_dir}" \
  --cell-width 500 \
  --cell-height 550 \
  --font-size 40 \
  --autocrop \
  --image-scale 1.0
```

Recommended starting dimensions by orientation are:

| Orientation | Split | Slice | Cell width | Cell height |
| --- | --- | ---: | ---: | ---: |
| Axial (`ax`) | `xsplit` | 0.5 | 500 | 550 |
| Coronal (`cor`) | `xsplit` | 0.5 | 550 | 500 |
| Sagittal (`sag`) | `xsplit` | 0.6 | 550 | 400 |

For multiple subjects, list every subject after `--subjects`:

```bash
fslpython "${scripts_dir}/subject_contrasts_single_orientation.py" \
  --base-dir "${base_dir}" \
  --space "${space}" \
  --subjects TAGL_2p4e BXTF_1p2d \
  --orientation ax \
  --split xsplit \
  --slice 0.5 \
  --threshold "${thresh_type}" \
  --output-dir "${figure_dir}" \
  --cell-width 500 \
  --cell-height 550 \
  --font-size 40 \
  --autocrop \
  --image-scale 1.0
```

### Step 6: Optionally resample T2w-space LSM data

Use a NIfTI reference on the desired target grid. The script infers the target isotropic resolution from this reference and writes to `${base_dir}/${subject}/${space}/${resolution}um` unless `--output-dir` is supplied.

For example, resample the T2w-space outputs to a 150-µm reference grid:

```bash
space=t2w
ref_vol=/path/to/t2w_reference_150um.nii.gz

sh "${scripts_dir}/resample_niftys.sh" \
  --base-dir "${base_dir}" \
  --space "${space}" \
  --subject "${subject}" \
  --ref "${ref_vol}"
```

An identity matrix file named `ident.mat` must be available where expected by the script. Add `--output-dir /path/to/output` to override the default destination.

## Validate the completed workflow

Before downstream analysis or figure generation, confirm that:

1. the forward-transformed LSM NeuN image aligns with the T2w target;
2. the other LSM channels and maps align with the transformed NeuN image in T2w space;
3. the inverse-transformed T2w image aligns with the original LSM data;
4. all outputs have the expected dimensions, voxel sizes, affine, and orientation; and
5. the selected figure slices, split directions, thresholds, and atlas boundaries are correct.

## Notes for reproducibility

- Record the stain-to-channel assignment for every acquisition.
- Preserve the registration configuration file and output directory with each run.
- Record the NeuN preprocessing threshold (`250`) and square-root transform.
- Record all visualization slice positions, threshold modes, split directions, and scaling parameters.
- Treat institutional paths, FSL modules, and output locations as deployment-specific configuration.
