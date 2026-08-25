"""
Configuration constants for the LSM Segmentation Pipeline.
"""
from pathlib import Path

# =============================================================================
# Path Configuration
# =============================================================================

# Root directories
# RAW_DATA_ROOT = Path("/well/lerch/users/mjm485/lsm_data/MAIN_PHASE")
RAW_DATA_ROOT = Path("/data/WT_bioimaging/MAIN_PHASE_LSM")

# PROCESSED_DATA_ROOT = Path("/well/lerch/users/mjm485/LSMSeg/data/MAIN_PHASE")
PROCESSED_DATA_ROOT = Path("/home/mszsa9/WT_LSM_reg_pipeline/downsample_test/LSMSeg_test")

SCRIPTS_DIR = Path(__file__).parent

# Ilastik installation and project
#ILASTIK_DIR = Path("/well/lerch/users/mjm485/ilastik-1.4.1.post1-Linux")
#ILASTIK_PROJECT = PROCESSED_DATA_ROOT / "BXTT_1p1b_NeuN_GFAP/4xobj_1p66xzoom_4um_step/13-57-41_BXTT1p1b_high_mag_4um_step_lsm_fast_tile3x_5x7_15pc_Blaze_C00/saf/for_train_test/gfap.ilp"

# Cellpose model paths
#CELLPOSE_MODEL_C01 = "/well/lerch/users/mjm485/LSMSeg/data/train_models/neun/CP_20251011_151301"

# =============================================================================
# Processing Parameters
# =============================================================================

# Voxel size for 4x objective (Z, Y, X in micrometers)
VOXEL_SIZE_4X = (4.0, 0.98, 0.98)
#VOXEL_SIZE_4X = (4.0, 1.0, 1.0)

# Downsampling factors
# DS_VISUALIZATION = (8, 32, 32)   # For quick visualization (tif/nii output)
DS_VISUALIZATION = (8, 32, 32)

# DS_PARAMETER_MAPS = (32, 128, 128)  # For SAF and cell count maps
#DS_PARAMETER_MAPS = (4, 16, 16)
DS_PARAMETER_MAPS = (8, 32, 32)

# HDF5 chunk size
H5_CHUNK_SIZE = (64, 256, 256)

# Cellpose processing parameters
#CELLPOSE_BLOCK_SIZE = (64, 512, 512)
#CELLCOUNT_BIN_SIZE = (1, 4, 4)
CELLCOUNT_BIN_SIZE = (8, 32, 32)
CELLPOSE_HALO = (0, 0, 0)

# Ilastik memory limit (MB)
ILASTIK_RAM_MB = 64000

# =============================================================================
# SLURM Configuration
# =============================================================================

# Conda environment for cellpose GPU
CELLPOSE_CONDA_ENV = "cellpose3-p100"

# SLURM partitions
SLURM_PARTITION_GPU = "gpu_short"
SLURM_PARTITION_CPU = "short"

# Resource defaults
SLURM_MEM_CONVERT = "32G"
SLURM_MEM_ILASTIK = "64G"
SLURM_MEM_CELLPOSE = "20G"
SLURM_CPUS_CELLPOSE = 2

# =============================================================================
# Channel Configuration
# =============================================================================

CHANNELS = {
    "C00": {
        "name": "GFAP",
        "description": "Glial Fibrillary Acidic Protein (astrocyte marker)",
        "processing": "ilastik_saf",  # ilastik segmentation -> SAF calculation
    },
    "C01": {
        "name": "NeuN",
        "description": "Neuronal Nuclear Antigen (neuron marker)",
        "processing": "cellpose",  # cellpose cell counting
    },
}

# =============================================================================
# Output Naming Conventions
# =============================================================================

def get_output_h5_path(strain: str, session: str, channel: str) -> Path:
    """Get the path for the output HDF5 file."""
    return PROCESSED_DATA_ROOT / strain / "4xobj_1p66xzoom_4um_step" / f"{session}_C{channel:02d}.h5"

def get_output_saf_path(strain: str, session: str, ds: tuple = DS_PARAMETER_MAPS) -> Path:
    """Get the path for the SAF output."""
    ds_str = f"{ds[0]}x{ds[1]}x{ds[2]}"
    return PROCESSED_DATA_ROOT / strain / "4xobj_1p66xzoom_4um_step" / f"{session}_C00" / f"saf_ds{ds_str}.tif"

def get_output_cellcount_path(strain: str, session: str, ds: tuple = DS_PARAMETER_MAPS) -> Path:
    """Get the path for the cell count output."""
    ds_str = f"{ds[0]}x{ds[1]}x{ds[2]}"
    strain_short = strain.replace("_NeuN_GFAP", "")
    return (PROCESSED_DATA_ROOT / strain / "4xobj_1p66xzoom_4um_step" / f"{session}_C01" /
            "cellpose3_2d_outputs" / f"{strain_short}_NeuN_cell_counts_ds{ds_str}_reoriented.nii.gz")
