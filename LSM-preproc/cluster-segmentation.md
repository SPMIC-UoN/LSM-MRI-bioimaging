# Cluster segmentation and output stitching

**Author:** Martin Craig
**Original workflow documentation:** August 2026

This guide covers Steps 2–5 of the [main workflow](../README.md): running Cellpose and ilastik on HDF5 volumes with SLURM, then stitching their block-level outputs into NIfTI maps.

## Before submitting jobs

You need:

- a downsampled HDF5 file for each stain/channel;
- a correctly oriented, downsampled NIfTI reference image for the NeuN channel;
- the confirmed mapping between stains and acquisition channels; and
- enough storage for all intermediate block outputs.

> [!CAUTION]
> Channel numbering is acquisition-dependent. Verify which HDF5 file contains NeuN and which contains GFAP. Do not assign stains from `C00` or `C01` alone.

At the original deployment site, the batch scripts use the `ampereq` GPU partition, activate `/software/imaging/miniconda3/envs/cellpose`, and load the `ilastik-img` module. Update these settings for your cluster.

## Configure the segmentation jobs

Edit `batch_c0.sh` and `batch_c1.sh` so that each points to the corresponding HDF5 input. For example:

```bash
base_dir=/path/to/processed-data
dataset=TAGL_2p4e_NeuN_GFAP
acquisition_dir="${base_dir}/${dataset}/4xobj_1p66xzoom_4um_step"

H5_FILE="${acquisition_dir}/<acquisition>_C00.h5"
```

Set `H5_FILE` to the C00 input in `batch_c0.sh` and to the C01 input in `batch_c1.sh`.

Both batch scripts call `run_h5.py`. The script uses the configured input naming/channel information to dispatch the appropriate processing:

- `run_cellpose.py` for the NeuN channel;
- `run_ilastik.py` for the GFAP channel.

Confirm that the dispatch logic identifies your stains correctly before launching a full run.

## Submit the segmentation jobs

```bash
sbatch batch_c0.sh
sbatch batch_c1.sh
```

The supplied configuration uses 100 array tasks. Change the SLURM array definition in `batch_c0.sh` and `batch_c1.sh` and the matching worker setting in `run_h5.py` together; the relevant locations are marked `FIXME` in the scripts.

## Software and resources

The original cluster configuration uses:

- Cellpose 3.1.1.3;
- CUDA-enabled PyTorch from the `cellpose` Conda environment;
- ilastik 1.4.2 GPU executables supplied by `ilastik-img`; and
- one GPU per array task on the `ampereq` partition.

Typical runtimes on that system were:

| Process | Time per array task | Approximate total wall time* |
| --- | ---: | ---: |
| Cellpose | 30–45 min | 8–12 h |
| ilastik | up to 2 h | about 30 h |

\*Estimates assume at most six GPU jobs run concurrently. Queueing, hardware, input size, and storage performance will change these values.

Both processing scripts skip blocks that already have complete outputs. After a partial failure, it is therefore safe to resubmit the same job; completed blocks will not be recomputed. Check the logs and available storage before restarting.

## Stitch block outputs

After both segmentation jobs finish, edit `batch_stitch.sh` with the output directories and NeuN reference NIfTI. For example:

```bash
base_dir=/path/to/processed-data
dataset=TAGL_2p4e_NeuN_GFAP
acquisition_dir="${base_dir}/${dataset}/4xobj_1p66xzoom_4um_step"

FOLDER_CELLPOSE="${acquisition_dir}/<neun-acquisition>/cellpose3_2d_outputs/bs64_512_512-vs8_32_32"
FOLDER_ILASTIK="${acquisition_dir}/<gfap-acquisition>/saf/outputs"
CELLPOSE_REF="${acquisition_dir}/<neun-acquisition>_ds8x32x32.nii.gz"
```

Only `FOLDER_CELLPOSE`, `FOLDER_ILASTIK`, and `CELLPOSE_REF` are required; the other variables simply keep paths readable.

Submit the stitching job:

```bash
sbatch batch_stitch.sh
```

Stitching is not GPU-intensive and generally completes in under 15 minutes, so the supplied job does not request a GPU.

The wrapper combines the Cellpose and ilastik block outputs into quantitative NIfTI maps. If the wrapper is unavailable or you need finer control, use the direct stitching commands in [Steps 4 and 5 of the main README](../README.md#4-create-neun-cell-count-and-cell-density-maps).

## Validate the outputs

Before downstream analysis:

1. Check the SLURM logs for failed or missing array tasks.
2. Confirm that the stitched NIfTIs have the expected dimensions and voxel sizes.
3. Open the reference images and maps together in a NIfTI viewer.
4. Verify orientation and voxelwise alignment throughout the volume.
5. Confirm that the cell-count, density, and stain-fraction values are plausible.
