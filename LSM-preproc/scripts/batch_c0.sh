#!/bin/sh
#SBATCH --time=04:00:00
#SBATCH --job-name=h5proc
#SBATCH --partition=ampereq,ampere-mq
##SBATCH --partition=imgvoltaq
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=64g
#SBATCH --gres=gpu:1
#SBATCH --export=NONE
##SBATCH --qos=img
#SBATCH --array=0-100
#SBATCH --output logs/%A_%a.out
#SBATCH --error logs/%A_%a.err

module load cuda-12.2.2
module load conda-img
module load ilastik-img/gpu
source activate cellpose

BASE=/imgshare/RodentMRI/WT_BioImaging_2026/
#DATASET=$BASE/BXTB_1p1e/
#H5_FILE=$DATASET/downsample_test/$DATASET/4xobj_1p66xzoom_4um_step/14-38-38_4xobj_1p66xzoom_BXTB_1p1e_4um_ls_fst_3x_10pc_Blaze_C00.h5
#DATASET=BXTD_1p1a
#H5_FILE=$BASE/$DATASET/downsample_test/$DATASET/4xobj_1p66xzoom_4um_step/17-28-54_BXTD_1p1a_Blaze_C01.h5
#DATASET=BXTA_1p3a_NeuN_GFAP
#H5_FILE=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/14-05-14_BXTA_1p3a_2_Blaze_C00.h5
#DATASET=BXTC_1p2a_NeuN_GFAP
#H5_FILE=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/251021_BXTC_1p2A_4x_1p66_12-23-48/12-23-48_BXTC_1p2A_4x_1p66_Blaze_C00.h5 
#DATASET=BXTF_1p2d_NeuN_GFAP
#H5_FILE=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/12-09-44_4x_1p66xx_BXTF_1p2_561_640_ls_ft3_Blaze_C00.h5
#DATASET=BXTH_1p1c_NeuN_GFAP
#H5_FILE=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/251022_BXTH_1p2c_4x_1p66_17-00-59/17-00-59_BXTH_1p2c_4x_1p66_Blaze_C00.h5

#DATASET=BXTT_1p2a_NeuN_GFAP
#H5_FILE=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/12-56-07_BXTT_1p2a_4xz_1p66xo_4um_Blaze_C00.h5

DATASET=TAGL_2p4e_NeuN_GFAP
H5_FILE=$BASE/$DATASET/4xobj_1p66xzoom_4um_step/12-14-08_TAGL_2p4e_4xo_1p66xz_4um_ls_ft3_Blaze_C00.h5

python run_h5.py --h5 $H5_FILE
