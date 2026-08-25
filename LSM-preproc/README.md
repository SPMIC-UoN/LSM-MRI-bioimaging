# Light-sheet microscopy processing pipeline

**Author:** Stephania Assimopoulos
**Original workflow documentation:** August 2026

This repository converts multichannel OME-TIFF light-sheet microscopy (LSM) data into spatially aligned NIfTI images and quantitative maps. The workflow supports:

- OME-TIFF conversion to downsampled NIfTI and HDF5 (`.h5`)
- NeuN cell segmentation with Cellpose
- GFAP foreground segmentation with ilastik
- NeuN cell-count and cell-density maps
- GFAP stain-area-fraction maps

GPU-based Cellpose and ilastik processing is designed for a SLURM cluster. Conversion, stitching, and map generation use FSL Python and can run without a GPU.

## Workflow

| Step | Input | Operation | Main output |
| --- | --- | --- | --- |
| 1 | Channel OME-TIFFs | Convert and downsample | NIfTI reference images and HDF5 volumes |
| 2 | NeuN HDF5 | Cellpose segmentation | Block-level `.npy` masks/counts |
| 3 | GFAP HDF5 | ilastik segmentation | Block-level TIFF probability/label images |
| 4 | Cellpose outputs | Stitch and calculate density | NeuN cell-count and cell-density NIfTIs |
| 5 | ilastik outputs | Stitch stain fractions | GFAP stain-area-fraction NIfTI |

> [!IMPORTANT]
> Do not assume that `C00` or `C01` always represents the same stain. Confirm the NeuN and GFAP channel assignments from the acquisition metadata or filenames before processing. The example commands below use descriptive placeholders for this reason.

## Requirements

- Python environment containing the packages imported by the processing scripts
- FSL 6.0.7.x (including `fslpython`)
- A CUDA-capable GPU for practical Cellpose and ilastik runtimes
- Cellpose 3.1.1.3
- ilastik 1.4.2 with GPU support
- SLURM for the supplied batch scripts

Site-specific module names, environments, partitions, and paths should be updated for your cluster. At the original deployment site, scripts were stored in:


## Input layout

The conversion script expects a directory resembling:

```text
<main_tif_dir>/
└── <subject_or_strain>/
    └── <magnification>/
        ├── <acquisition>_C00.ome.tif
        └── <acquisition>_C01.ome.tif
```

The exact acquisition layout may differ. Inspect it before running the pipeline.

## Run the pipeline: one-subject example

This walkthrough processes `TAGL_2p4e` from raw OME-TIFFs to quantitative NIfTI maps. Copy the commands in order, replacing paths and acquisition names for your data.

### Set the run configuration

```bash
scripts_dir=/imgshare/RodentMRI/WT_BioImaging_2026/scripts
main_tif_dir=/path/to/ome-tiff-data
subject=TAGL_2p4e
magnification=4xobj_1p66xzoom_4um_step
output_dir=/path/to/processed-data

# Downsampling from approximately 4.00 x 0.98 x 0.98 um to approximately
# 30 x 30 x 30 um. Confirm these values for your acquisition.
ds_z=8
ds_y=32
ds_x=32
```

For this example, assume acquisition metadata confirms that NeuN is `C01` and GFAP is `C00`. Reverse those assignments if required for your acquisition.

### Step 1: Convert OME-TIFF channels to NIfTI and HDF5

Preview the conversion first:

```bash
module load fsl/6.0.7.x

fslpython "${scripts_dir}/convert_tiff2nifty_mem_fix.py" \
  --main_dir "${main_tif_dir}" \
  --strains "${subject}" \
  --mag "${magnification}" \
  --ds_factor "${ds_z}" "${ds_y}" "${ds_x}" \
  --out_dir "${output_dir}" \
  --keep_h5 \
  --dry-run
```

If the paths and detected inputs are correct, run the same command without `--dry-run`:

```bash
fslpython "${scripts_dir}/convert_tiff2nifty_mem_fix.py" \
  --main_dir "${main_tif_dir}" \
  --strains "${subject}" \
  --mag "${magnification}" \
  --ds_factor "${ds_z}" "${ds_y}" "${ds_x}" \
  --out_dir "${output_dir}" \
  --keep_h5
```

Notes:

- Add `--channel 0` or `--channel 1` to process only one channel.
- Keep `--keep_h5` on the first run because Steps 2 and 3 require the HDF5 outputs.

The resulting downsampled NIfTI image for each channel serves as the spatial reference when its block-level outputs are stitched.

### Steps 2–3: Run Cellpose and ilastik on the cluster

These steps require the two downsampled HDF5 files created in Step 1 and the correctly oriented, downsampled NeuN NIfTI that will later serve as the stitching reference.

The supplied batch scripts request a GPU on the `ampereq` partition. At the original deployment site they activate the `cellpose` Conda environment (eg `/software/imaging/miniconda3/envs/cellpose`) and load `ilastik-img`. 
This requires Cellpose 3.1.1.3, CUDA-enabled PyTorch, and GPU-enabled ilastik 1.4.2. Update the partition, modules, and environment paths for your cluster.

Locate the two HDF5 files created in Step 1. Edit `batch_c0.sh` and `batch_c1.sh` so each script points to its matching channel:

```bash
# In batch_c0.sh
H5_FILE="/path/to/processed-data/TAGL_2p4e/<C00-acquisition>.h5"

# In batch_c1.sh
H5_FILE="/path/to/processed-data/TAGL_2p4e/<C01-acquisition>.h5"
```

Submit both channel jobs:

```bash
sbatch "${scripts_dir}/batch_c0.sh"
sbatch "${scripts_dir}/batch_c1.sh"
```

`run_h5.py` dispatches the confirmed NeuN channel to Cellpose and the GFAP channel to ilastik. Check both SLURM arrays and wait for them to finish successfully before continuing.

The scripts currently use 100 array workers. If that must change, update both the SLURM array setting in `batch_c0.sh`/`batch_c1.sh` and the corresponding worker value in `run_h5.py`; the relevant locations are marked `FIXME`.

Typical runtimes on the original cluster were:

| Process | Per array task | Approximate total wall time* |
| --- | ---: | ---: |
| Cellpose | 30–45 min | 8–12 h |
| ilastik | up to 2 h | about 30 h |

\*These estimates assume no more than six GPU jobs run simultaneously. Queueing, hardware, data size, and storage performance will affect them.

Both `run_cellpose.py` and `run_ilastik.py` skip blocks that already have complete outputs. If a job stops partway through—for example, because storage fills—it is safe to correct the problem and resubmit the whole job. Only incomplete blocks will run again.

See the [cluster segmentation guide](docs/cluster-segmentation.md) for resource configuration, expected runtimes, array-worker settings, restart behaviour, and troubleshooting.

### Steps 4–5: Stitch the segmentation outputs

After both arrays finish, edit `batch_stitch.sh` with the Cellpose output directory, ilastik output directory, and downsampled NeuN reference from Step 1:

```bash
FOLDER_CELLPOSE="/path/to/processed-data/TAGL_2p4e/<neun-acquisition>/cellpose3_2d_outputs/bs64_512_512-vs8_32_32"
FOLDER_ILASTIK="/path/to/processed-data/TAGL_2p4e/<gfap-acquisition>/saf/outputs"
CELLPOSE_REF="/path/to/processed-data/TAGL_2p4e/<neun-acquisition>_ds8x32x32.nii.gz"
```

Submit the stitching job:

```bash
sbatch "${scripts_dir}/batch_stitch.sh"
```

This produces the NeuN cell-count map and GFAP stain-area-fraction map. Stitching normally requires no GPU.

`batch_stitch.sh` combines the Cellpose and ilastik block outputs into individual NIfTI maps. On the original cluster it generally finished in less than 15 minutes.

### Create the NeuN cell-density map

Pass the stitched cell-count NIfTI to the density script:

```bash
cell_count_nifti=/path/to/processed-data/TAGL_2p4e/cell_count_map.nii.gz

sh "${scripts_dir}/get_cellcount_density.sh" \
  "${cell_count_nifti}"
```

The main pipeline is now complete. Continue to [Check the completed outputs](#check-the-completed-outputs).

## Direct stitching commands

Use these commands instead of `batch_stitch.sh` when the wrapper is unavailable or you need to control the stitching options directly.

### NeuN cell-count map

```bash
module load fsl/6.0.7.x

fslpython "${scripts_dir}/stitch_cellcounts_final.py" \
  --folder "${cellpose_output_dir}" \
  --ref "${neun_reference_nifti}" \
  --bin-size 1 4 4 \
  --ds-factor "${ds_z}" "${ds_y}" "${ds_x}" \
  --output-dir "${map_output_dir}"
```

Then convert the cell-count map to a cell-density map:

```bash
sh "${scripts_dir}/get_cellcount_density.sh" "${cell_count_nifti}"
```

`--ds-factor` must match Step 1. `--bin-size` describes the Cellpose count bins and is independent of the image downsampling factor; use the value with which the Cellpose outputs were generated (current default: `1 4 4`). The reference NIfTI supplies the output grid, affine, and orientation.

### GFAP stain-area-fraction map

```bash
module load fsl/6.0.7.x

fslpython "${scripts_dir}/stitch_saf_final.py" \
  --folder "${ilastik_output_dir}" \
  --ds-factor "${ds_z}" "${ds_y}" "${ds_x}" \
  --voxel-size 4.0 0.98 0.98 \
  --output-dir "${map_output_dir}"
```

The voxel size shown above matches the original acquisition. Change it when processing data acquired at a different resolution.

## Check the completed outputs

At completion, the downsampled channel images and derived quantitative maps should share the same NIfTI grid, resolution, affine, and orientation:

- NeuN reference image
- GFAP reference image
- NeuN cell-count map
- NeuN cell-density map
- GFAP stain-area-fraction map

Before downstream registration or analysis, visually inspect all outputs together and verify their dimensions and spatial metadata. The [cluster guide](docs/cluster-segmentation.md) contains a more detailed validation checklist.

## Notes for reproducibility

- Record the stain-to-channel assignment for every acquisition.
- Keep the OME-TIFF voxel size, downsampling factor, Cellpose bin size, and software versions with each run.
- Use the same downsampling factor during conversion and stitching.
- Treat cluster paths and resource requests as deployment-specific configuration.
