#!/usr/bin/env bash

# Resample NIfTI files to the voxel grid of a reference image.
#
# The output resolution, dimensions, orientation, affine, and field of view
# are determined by the reference image supplied with --ref.
#
# Default output-directory naming:
#   Isotropic reference:
#       0.150 x 0.150 x 0.150 mm -> 150um
#
#   Anisotropic reference:
#       0.016 x 0.016 x 0.032 mm -> 16x16x32um
#
# The original image for the selected space and its corresponding mask are
# not resampled:
#
#   SPACE.nii.gz
#   SPACE_mask.nii.gz
#
# All other NIfTI files in the input directory are processed, including files
# whose names contain the space value as part of a longer filename.
#
# The reference image is copied into the output directory as:
#
#   SPACE.nii.gz
#
# Author: Stephania Assimopoulos

set -euo pipefail

# -------------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------------

base_dir=""
subject=""
space=""
ref=""
output_dir=""
identity_mat=""

fsl_module="fsl/6.0.7.x"

overwrite=false

# -------------------------------------------------------------------------
# Help
# -------------------------------------------------------------------------

usage() {
    cat << EOF

Usage:
    $(basename "$0") \\
        --base-dir BASE_DIR \\
        --subject SUBJECT \\
        --space SPACE \\
        --ref REFERENCE_IMAGE [OPTIONS]

Required arguments:
    --base-dir DIR
        Base directory containing the subject directories.

    --subject ID
        Subject or strain identifier.

    --space NAME
        Input-space directory located at:

            BASE_DIR/SUBJECT/SPACE

        The following files are excluded from resampling:

            SPACE.nii.gz
            SPACE_mask.nii.gz

        Files containing the space name as part of a longer filename are
        still processed.

        For example, with:

            --space t2w

        these are skipped:

            t2w.nii.gz
            t2w_mask.nii.gz

        while these are processed:

            4xobj_GFAP_to_t2w_cubic.nii.gz
            GFAP_map_to_t2w_cubic.nii.gz

    --ref FILE
        Reference NIfTI image.

        The reference determines the output:
            - voxel size
            - image dimensions
            - orientation
            - affine
            - field of view

        A copy of the reference is saved in the output directory as:

            SPACE.nii.gz

Optional arguments:
    --output-dir DIR
        Custom output directory.

        By default, the output directory is created inside the input-space
        directory and named using the voxel size inferred from the reference.

        Examples:
            BASE_DIR/SUBJECT/SPACE/150um
            BASE_DIR/SUBJECT/SPACE/16x16x32um

    --identity-mat FILE
        Identity transformation matrix.

        Default:
            BASE_DIR/SUBJECT/ident.mat

    --fsl-module MODULE
        FSL module to load.

        Default:
            ${fsl_module}

    --overwrite
        Overwrite resampled output files that already exist.

        The reference copy SPACE.nii.gz is always replaced so that it matches
        the reference supplied in the current command.

    -h, --help
        Show this help message and exit.

Example:
    $(basename "$0") \\
        --base-dir ./ \\
        --subject TAGL_2p4e \\
        --space t2w \\
        --ref /path/to/reference_150um.nii.gz

EOF
}

# -------------------------------------------------------------------------
# Check that an option has a value
# -------------------------------------------------------------------------

require_value() {
    local option="$1"
    local value="${2-}"

    if [[ -z "$value" || "$value" == --* ]]; then
        echo "ERROR: ${option} requires a value." >&2
        exit 1
    fi
}

# -------------------------------------------------------------------------
# Parse command-line arguments
# -------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-dir)
            require_value "$1" "${2-}"
            base_dir="$2"
            shift 2
            ;;

        --subject)
            require_value "$1" "${2-}"
            subject="$2"
            shift 2
            ;;

        --space)
            require_value "$1" "${2-}"
            space="$2"
            shift 2
            ;;

        --ref)
            require_value "$1" "${2-}"
            ref="$2"
            shift 2
            ;;

        --output-dir)
            require_value "$1" "${2-}"
            output_dir="$2"
            shift 2
            ;;

        --identity-mat)
            require_value "$1" "${2-}"
            identity_mat="$2"
            shift 2
            ;;

        --fsl-module)
            require_value "$1" "${2-}"
            fsl_module="$2"
            shift 2
            ;;

        --overwrite)
            overwrite=true
            shift
            ;;

        -h|--help)
            usage
            exit 0
            ;;

        *)
            echo "ERROR: Unknown argument: $1" >&2
            echo "Run '$(basename "$0") --help' for usage information." >&2
            exit 1
            ;;
    esac
done

# -------------------------------------------------------------------------
# Validate required arguments
# -------------------------------------------------------------------------

missing_arguments=()

[[ -n "$base_dir" ]] || missing_arguments+=("--base-dir")
[[ -n "$subject" ]]  || missing_arguments+=("--subject")
[[ -n "$space" ]]    || missing_arguments+=("--space")
[[ -n "$ref" ]]      || missing_arguments+=("--ref")

if [[ ${#missing_arguments[@]} -gt 0 ]]; then
    echo "ERROR: Missing required argument(s):" >&2

    for argument in "${missing_arguments[@]}"; do
        echo "  $argument" >&2
    done

    echo "" >&2
    usage >&2
    exit 1
fi

# -------------------------------------------------------------------------
# Resolve paths
# -------------------------------------------------------------------------

base_dir=$(realpath -m "$base_dir")
ref=$(realpath -m "$ref")

input_dir="${base_dir}/${subject}/${space}"

if [[ -z "$identity_mat" ]]; then
    identity_mat="${base_dir}/${subject}/ident.mat"
else
    identity_mat=$(realpath -m "$identity_mat")
fi

# -------------------------------------------------------------------------
# Validate input paths
# -------------------------------------------------------------------------

if [[ ! -d "$base_dir" ]]; then
    echo "ERROR: Base directory does not exist:" >&2
    echo "  $base_dir" >&2
    exit 1
fi

if [[ ! -d "$input_dir" ]]; then
    echo "ERROR: Input directory does not exist:" >&2
    echo "  $input_dir" >&2
    exit 1
fi

if [[ ! -f "$ref" ]]; then
    echo "ERROR: Reference image does not exist:" >&2
    echo "  $ref" >&2
    exit 1
fi

if [[ ! "$ref" =~ \.nii(\.gz)?$ ]]; then
    echo "ERROR: Reference image must be a .nii or .nii.gz file:" >&2
    echo "  $ref" >&2
    exit 1
fi

if [[ ! -f "$identity_mat" ]]; then
    echo "ERROR: Identity matrix does not exist:" >&2
    echo "  $identity_mat" >&2
    exit 1
fi

# -------------------------------------------------------------------------
# Load FSL
# -------------------------------------------------------------------------

if type module >/dev/null 2>&1; then
    module load "$fsl_module"
else
    echo "WARNING: The 'module' command is unavailable." >&2
    echo "         Assuming FSL is already available in PATH." >&2
fi

for command_name in flirt fslval; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "ERROR: Required FSL command not found: $command_name" >&2
        exit 1
    fi
done

# -------------------------------------------------------------------------
# Infer output resolution from the reference image
# -------------------------------------------------------------------------

pixdim1=$(fslval "$ref" pixdim1)
pixdim2=$(fslval "$ref" pixdim2)
pixdim3=$(fslval "$ref" pixdim3)

for value in "$pixdim1" "$pixdim2" "$pixdim3"; do
    if ! awk -v value="$value" '
        BEGIN {
            if ((value + 0) > 0) {
                exit 0
            }

            exit 1
        }
    '
    then
        echo "ERROR: Invalid voxel size read from reference image: $value" >&2
        exit 1
    fi
done

# FSL reports voxel sizes in millimetres.
# Convert them to micrometres and remove unnecessary trailing zeros.

format_um() {
    local value_mm="$1"

    awk -v value="$value_mm" '
        BEGIN {
            value_um = value * 1000
            text = sprintf("%.6f", value_um)

            sub(/0+$/, "", text)
            sub(/\.$/, "", text)

            print text
        }
    '
}

pixdim1_um=$(format_um "$pixdim1")
pixdim2_um=$(format_um "$pixdim2")
pixdim3_um=$(format_um "$pixdim3")

# Determine whether the reference voxel size is isotropic.
#
# The comparison tolerance is 0.000001 mm, equivalent to 0.001 µm.

if awk \
    -v x="$pixdim1" \
    -v y="$pixdim2" \
    -v z="$pixdim3" '
        BEGIN {
            tolerance = 0.000001

            diff_xy = x - y
            diff_xz = x - z

            if (diff_xy < 0) {
                diff_xy = -diff_xy
            }

            if (diff_xz < 0) {
                diff_xz = -diff_xz
            }

            if (diff_xy <= tolerance && diff_xz <= tolerance) {
                exit 0
            }

            exit 1
        }
    '
then
    isotropic=true
    resolution_label="${pixdim1_um}um"
else
    isotropic=false
    resolution_label="${pixdim1_um}x${pixdim2_um}x${pixdim3_um}um"
fi

# -------------------------------------------------------------------------
# Set output directory
# -------------------------------------------------------------------------

if [[ -z "$output_dir" ]]; then
    output_dir="${input_dir}/${resolution_label}"
else
    output_dir=$(realpath -m "$output_dir")
fi

mkdir -p "$output_dir"

output_ref="${output_dir}/${space}.nii.gz"

# -------------------------------------------------------------------------
# Find input images
# -------------------------------------------------------------------------

shopt -s nullglob

candidate_files=(
    "$input_dir"/*.nii
    "$input_dir"/*.nii.gz
)

shopt -u nullglob

if [[ ${#candidate_files[@]} -eq 0 ]]; then
    echo "ERROR: No .nii or .nii.gz files were found in:" >&2
    echo "  $input_dir" >&2
    exit 1
fi

# -------------------------------------------------------------------------
# Filter input images
# -------------------------------------------------------------------------

input_files=()
space_skipped_files=()

for input_file in "${candidate_files[@]}"; do
    filename=$(basename "$input_file")

    if [[ "$filename" == *.nii.gz ]]; then
        stem="${filename%.nii.gz}"
    else
        stem="${filename%.nii}"
    fi

    # Skip only the original image for the selected space and its mask.
    #
    # For --space t2w:
    #   t2w.nii.gz       -> skipped
    #   t2w_mask.nii.gz  -> skipped
    #
    # Longer filenames containing "t2w" are still processed.

    if [[ "$stem" == "$space" || "$stem" == "${space}_mask" ]]; then
        space_skipped_files+=("$input_file")
        continue
    fi

    input_files+=("$input_file")
done

# -------------------------------------------------------------------------
# Print processing information
# -------------------------------------------------------------------------

echo ""
echo "Resampling NIfTI images"
echo "-----------------------"
echo "Subject:           $subject"
echo "Input space:       $space"
echo "Input directory:   $input_dir"
echo "Reference image:   $ref"
echo "Identity matrix:   $identity_mat"
echo "Output directory:  $output_dir"
echo "Candidate images:  ${#candidate_files[@]}"
echo "Images to process: ${#input_files[@]}"
echo ""
echo "Reference voxel size:"
echo "  ${pixdim1} x ${pixdim2} x ${pixdim3} mm"
echo "  ${pixdim1_um} x ${pixdim2_um} x ${pixdim3_um} um"
echo ""

if [[ "$isotropic" == true ]]; then
    echo "Reference grid:    isotropic"
else
    echo "Reference grid:    anisotropic"
fi

echo "Resolution label:  $resolution_label"
echo ""

if [[ ${#space_skipped_files[@]} -gt 0 ]]; then
    echo "Skipping the original '${space}' image and corresponding mask:"

    for skipped_file in "${space_skipped_files[@]}"; do
        echo "  $(basename "$skipped_file")"
    done

    echo ""
fi

# -------------------------------------------------------------------------
# Copy reference image
# -------------------------------------------------------------------------

echo "Copying reference image:"
echo "  Source:      $ref"
echo "  Destination: $output_ref"

if [[ "$ref" == *.nii.gz ]]; then
    cp -f "$ref" "$output_ref"
else
    gzip -c "$ref" > "$output_ref"
fi

echo ""

# -------------------------------------------------------------------------
# Resample images
# -------------------------------------------------------------------------

processed=0
existing_skipped=0
failed=0

for input_file in "${input_files[@]}"; do
    filename=$(basename "$input_file")

    if [[ "$filename" == *.nii.gz ]]; then
        stem="${filename%.nii.gz}"
    else
        stem="${filename%.nii}"
    fi

    output_file="${output_dir}/${stem}.nii.gz"

    if [[ -f "$output_file" && "$overwrite" == false ]]; then
        echo "Skipping existing output:"
        echo "  $output_file"
        echo ""

        ((existing_skipped += 1))
        continue
    fi

    echo "Processing:"
    echo "  Input:  $input_file"
    echo "  Output: $output_file"

    if flirt \
        -in "$input_file" \
        -ref "$ref" \
        -out "$output_file" \
        -init "$identity_mat" \
        -applyxfm
    then
        ((processed += 1))
    else
        echo "WARNING: FLIRT failed for:" >&2
        echo "  $input_file" >&2

        ((failed += 1))
    fi

    echo ""
done

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------

echo "Resampling complete."
echo "Processed:                $processed"
echo "Skipped source images:    ${#space_skipped_files[@]}"
echo "Skipped existing outputs: $existing_skipped"
echo "Failed:                   $failed"
echo ""
echo "Reference copy:"
echo "  $output_ref"
echo ""
echo "Output found in:"
echo "  $output_dir"
echo ""

if [[ $failed -gt 0 ]]; then
    exit 1
fi
