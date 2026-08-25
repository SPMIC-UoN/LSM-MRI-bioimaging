#!/bin/sh
#SBATCH --time=04:00:00
#SBATCH --job-name=stitch
#SBATCH --partition=defq
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=32g
#SBATCH --export=NONE
#SBATCH --output logs/%A_%a.out
#SBATCH --error logs/%A_%a.err

module load cuda-12.2.2
module load conda-img
module load ilastik-img/gpu
source activate cellpose

BASE=/imgshare/RodentMRI/WT_BioImaging_2026/
#DATASET=$BASE/BXTB_1p1e/
#FOLDER_H5=$DATASET/downsample_test/BXTB_1p1e/4xobj_1p66xzoom_4um_step/
#FOLDER_CELLPOSE=$FOLDER_H5/14-38-38_4xobj_1p66xzoom_BXTB_1p1e_4um_ls_fst_3x_10pc_Blaze_C01/cellpose3_2d_outputs/bs64_512_512-vs8_32_32/
#FOLDER_ILASTIK=$FOLDER_H5/14-38-38_4xobj_1p66xzoom_BXTB_1p1e_4um_ls_fst_3x_10pc_Blaze_C00/saf/outputs
#CELLPOSE_REF=$FOLDER_H5/14-38-38_4xobj_1p66xzoom_BXTB_1p1e_4um_ls_fst_3x_10pc_Blaze_C01_ds8x32x32.nii.gz
#DATASET=BXTD_1p1a/
#FOLDER_H5=$BASE/$DATASET/downsample_test/$DATASET/4xobj_1p66xzoom_4um_step/
#FOLDER_CELLPOSE=$FOLDER_H5/17-28-54_BXTD_1p1a_Blaze_C01/cellpose3_2d_outputs/bs64_512_512-vs8_32_32/
#FOLDER_ILASTIK=$FOLDER_H5/17-28-54_BXTD_1p1a_Blaze_C00/saf/outputs
#CELLPOSE_REF=$FOLDER_H5/17-28-54_BXTD_1p1a_Blaze_C01_ds8x32x32.nii.gz 
#DATASET=BXTA_1p3a_NeuN_GFAP
#FOLDER_H5=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/
#FOLDER_CELLPOSE=$FOLDER_H5/14-05-14_BXTA_1p3a_2_Blaze_C01/cellpose3_2d_outputs/bs64_512_512-vs8_32_32/
#FOLDER_ILASTIK=$FOLDER_H5/14-05-14_BXTA_1p3a_2_Blaze_C00/saf/outputs
#CELLPOSE_REF=$FOLDER_H5/BXTA_4xobj_NeuN.nii.gz

#DATASET=BXTC_1p2a_NeuN_GFAP
#FOLDER_H5=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/251021_BXTC_1p2A_4x_1p66_12-23-48/
#FOLDER_CELLPOSE=$FOLDER_H5/12-23-48_BXTC_1p2A_4x_1p66_Blaze_C01/cellpose3_2d_outputs/bs64_512_512-vs8_32_32/
#FOLDER_ILASTIK=$FOLDER_H5/12-23-48_BXTC_1p2A_4x_1p66_Blaze_C00/saf/outputs
#CELLPOSE_REF=$FOLDER_H5/12-23-48_BXTC_1p2A_4x_1p66_Blaze_C01.nii.gz

#DATASET=BXTF_1p2d_NeuN_GFAP
#FOLDER_H5=$BASE/$DATASET/4xobj_1p66xzoom_4um_step
#FOLDER_CELLPOSE=$FOLDER_H5/12-09-44_4x_1p66xx_BXTF_1p2_561_640_ls_ft3_Blaze_C00/cellpose3_2d_outputs/bs64_512_512-vs8_32_32
#FOLDER_ILASTIK=$FOLDER_H5/12-09-44_4x_1p66xx_BXTF_1p2_561_640_ls_ft3_Blaze_C01/saf/outputs
##CELLPOSE_REF=$FOLDER_H5/12-09-44_4x_1p66xx_BXTF_1p2_561_640_ls_ft3_Blaze_C00_ds8x32x32.nii.gz
#CELLPOSE_REF=$FOLDER_H5/BXTF_4xobj_NeuN.nii.gz

#DATASET=BXTH_1p1c_NeuN_GFAP
#FOLDER_H5=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/251022_BXTH_1p2c_4x_1p66_17-00-59
#FOLDER_CELLPOSE=$FOLDER_H5/17-00-59_BXTH_1p2c_4x_1p66_Blaze_C01/cellpose3_2d_outputs/bs64_512_512-vs8_32_32
#FOLDER_ILASTIK=$FOLDER_H5/17-00-59_BXTH_1p2c_4x_1p66_Blaze_C00/saf/outputs
#CELLPOSE_REF=$FOLDER_H5/17-00-59_BXTH_1p2c_4x_1p66_Blaze_C00_ds8x32x32.nii.gz

#DATASET=BXTT_1p2a_NeuN_GFAP
#FOLDER_H5=$BASE/$DATASET/4xobj_1p66xzoom_4um_step
#FOLDER_CELLPOSE=$FOLDER_H5/12-56-07_BXTT_1p2a_4xz_1p66xo_4um_Blaze_C01/cellpose3_2d_outputs/bs64_512_512-vs8_32_32/
#FOLDER_ILASTIK=$FOLDER_H5/12-56-07_BXTT_1p2a_4xz_1p66xo_4um_Blaze_C00/saf/outputs/
#CELLPOSE_REF=$FOLDER_H5/BXTT_4xobj_NeuN.nii.gz

DATASET=TAGL_2p4e_NeuN_GFAP
FOLDER_H5=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/
FOLDER_CELLPOSE=$FOLDER_H5/12-14-08_TAGL_2p4e_4xo_1p66xz_4um_ls_ft3_Blaze_C00/cellpose3_2d_outputs/bs64_512_512-vs8_32_32/
FOLDER_ILASTIK=$FOLDER_H5/12-14-08_TAGL_2p4e_4xo_1p66xz_4um_ls_ft3_Blaze_C01/saf/outputs/
CELLPOSE_REF=$FOLDER_H5/12-14-08_TAGL_2p4e_4xo_1p66xz_4um_ls_ft3_Blaze_C00_ds8x32x32.nii.gz

which python
python /gpfs01/imgshare/RodentMRI/WT_BioImaging_2026/scripts/stitch_cellcounts_final.py \
    --folder $FOLDER_CELLPOSE \
    --ref $CELLPOSE_REF

python /gpfs01/imgshare/RodentMRI/WT_BioImaging_2026/scripts/stitch_saf_final.py \
    --ds 8 32 32 \
    --folder $FOLDER_ILASTIK

