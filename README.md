# Towards high-throughput light-sheet 3D microscopy of whole rodent brain microstructure for integration with MRI Codebase

The pipeline moves whole-brain light-sheet microscopy data into a common MRI space and pairs it with diffusion MRI processing, in three independent sub-projects:

## [LSM-preproc](LSM-preproc/README.md)
Converts multichannel OME-TIFF light-sheet microscopy data into spatially aligned NIfTI/HDF5 volumes, then runs Cellpose (NeuN cell segmentation) and ilastik (GFAP segmentation) to produce cell-count, cell-density, and stain-area-fraction maps.

## [LSM-MRI-reg](LSM-MRI-reg/README.md)
Registers the light-sheet images and derived quantitative maps to ex vivo T2-weighted MRI, applies the inverse transform for LSM-space visualisation, and generates QC figures.

## [dMRI-preproc](dMRI-preproc/README.md)
Diffusion MRI preprocessing and biophysical modelling pipeline for the ex vivo mouse-brain dMRI data.