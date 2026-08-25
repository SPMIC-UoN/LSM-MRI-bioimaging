#!/usr/bin/env bash

set -euo pipefail


# =============================================================================
# Description
# =============================================================================

# This script is meant to be run once all registrations are complete in order
# to apply the necessary warps and bring the LSM-derived data into T2w space.
#
# Author: Stephania Assimopoulos
#
# Required registration:
#   Thresholded and square-root-transformed 4xobj NeuN --> T2w
#
# All LSM-derived images are assumed to already be aligned in the same
# 4xobj space.
#
# The acquired transforms are applied to:
#   1. NeuN channel
#   2. GFAP channel
#   3. NeuN cell-count map
#   4. GFAP map
#
#
# Expected default directory structure:
#
#   ${base_dir}/${subject}/data
#
# Expected files in the default data directory:
#
#   4xobj_NeuN.nii.gz
#   4xobj_GFAP.nii.gz
#   NeuN_map.nii.gz
#   NeuN_map_density.nii.gz
#   GFAP_map.nii.gz
#   t2w.nii.gz
#
#
# By default, the output directories are:
#
#   ${base_dir}/${subject}/4xobj
#   ${base_dir}/${subject}/t2w
#
# An alternative output parent directory can be supplied with --output_dir.
# In that case, the script creates:
#
#   ${output_dir}/4xobj
#   ${output_dir}/t2w
#
#
# Input-selection behaviour:
#
#   Neither --input_file nor --input_dir:
#       Process the four expected files from:
#           ${base_dir}/${subject}/data
#
#   --input_file only:
#       Process the specified file from:
#           ${base_dir}/${subject}/data
#
#   --input_file and --input_dir:
#       Process the specified file from:
#           ${input_dir}
#
#   --input_dir only:
#       Process every .nii.gz file directly inside:
#           ${input_dir}
#
#
# Relative paths such as ".", "./.", and ".." are converted to complete
# absolute paths before they are printed or used.


# =============================================================================
# Usage/help message
# =============================================================================

usage()
{
    cat <<EOF
Usage:
  $(basename "$0") \\
      --script_dir <directory> \\
      --base_dir <directory> \\
      --subject <subject_id> \\
      --reg_dir <registration_directory> \\
      [--input_file <filename.nii.gz>] \\
      [--input_dir <directory>] \\
      [--output_dir <directory>]

Description:
  Apply completed registration transforms between 4xobj and T2w space.

  Forward transform:

      4xobj --> T2w

  Reverse transform:

      T2w --> 4xobj


Required arguments:

  --script_dir <directory>
      Directory containing applywarp.py.

  --base_dir <directory>
      Base directory containing the subject directory.

      Relative paths are accepted. For example:

          --base_dir .
          --base_dir ./.
          --base_dir ..

      The path is converted to its full absolute form before processing.

  --subject <subject_id>
      Subject identifier.

  --reg_dir <directory>
      Registration-directory name or absolute path.

      A relative value is interpreted as:

          <base_dir>/<subject>/<reg_dir>

      An absolute path is used directly.


Optional input arguments:

  --input_file <filename.nii.gz>
      Process one specific NIfTI file.

      Without --input_dir, the file is read from:

          <base_dir>/<subject>/data

      With --input_dir, the file is read from:

          <input_dir>

  --input_dir <directory>
      Directory containing the input file or files.

      When supplied without --input_file, every .nii.gz file directly
      inside the directory is processed.


Optional output argument:

  --output_dir <directory>
      Parent directory in which the output-space directories are created.

      This creates:

          <output_dir>/4xobj
          <output_dir>/t2w

      If omitted, the default output directories are:

          <base_dir>/<subject>/4xobj
          <base_dir>/<subject>/t2w


Other:

  -h, --help
      Display this help message and exit.


Default files:

  If neither --input_file nor --input_dir is supplied, the following files
  are processed from <base_dir>/<subject>/data:

      4xobj_NeuN.nii.gz
      4xobj_GFAP.nii.gz
      NeuN_map.nii.gz
      NeuN_map_density.nii.gz
      GFAP_map.nii.gz


Examples:

  1. Process all four expected files using the current working directory
     as the base directory:

      $(basename "$0") \\
          --script_dir /path/to/scripts \\
          --base_dir ./. \\
          --subject BXTH_1p2c \\
          --reg_dir reg_4xobj_NeuN_to_t2w


  2. Process one file from the default subject data directory:

      $(basename "$0") \\
          --script_dir /path/to/scripts \\
          --base_dir /path/to/project \\
          --subject BXTH_1p2c \\
          --reg_dir reg_4xobj_NeuN_to_t2w \\
          --input_file NeuN_map.nii.gz


  3. Process one file from another directory:

      $(basename "$0") \\
          --script_dir /path/to/scripts \\
          --base_dir /path/to/project \\
          --subject BXTH_1p2c \\
          --reg_dir reg_4xobj_NeuN_to_t2w \\
          --input_file NeuN_map.nii.gz \\
          --input_dir /path/to/maps


  4. Process every .nii.gz file in another directory:

      $(basename "$0") \\
          --script_dir /path/to/scripts \\
          --base_dir /path/to/project \\
          --subject BXTH_1p2c \\
          --reg_dir reg_4xobj_NeuN_to_t2w \\
          --input_dir /path/to/maps


  5. Use a custom output parent directory:

      $(basename "$0") \\
          --script_dir /path/to/scripts \\
          --base_dir /path/to/project \\
          --subject BXTH_1p2c \\
          --reg_dir reg_4xobj_NeuN_to_t2w \\
          --output_dir /path/to/output/BXTH_1p2c

EOF
}


# =============================================================================
# Helper function for options requiring a value
# =============================================================================

require_option_value()
{
    local option_name=$1
    local option_value="${2:-}"

    if [[ -z "$option_value" || "$option_value" == --* ]]; then
        echo "ERROR: ${option_name} requires a value." >&2
        echo "" >&2
        usage >&2
        exit 1
    fi
}


# =============================================================================
# Helper function: convert a path to its full absolute path
#
# realpath -m/readlink -m allow the final directory to be missing. This is
# necessary for --output_dir because the directory may not exist yet.
# =============================================================================

resolve_path()
{
    local path=$1

    if command -v realpath >/dev/null 2>&1; then
        realpath -m -- "$path"
    elif command -v readlink >/dev/null 2>&1; then
        readlink -m -- "$path"
    else
        echo "ERROR: Neither realpath nor readlink is available." >&2
        echo "Cannot convert paths to their absolute form." >&2
        exit 1
    fi
}


# =============================================================================
# Initialise argument variables
# =============================================================================

script_dir=""
base_dir=""
subject=""
reg_dir=""

input_file=""
input_dir=""
output_dir=""


# =============================================================================
# Parse named command-line arguments
# =============================================================================

while [[ $# -gt 0 ]]; do

    case "$1" in

        --script_dir)
            require_option_value "$1" "${2:-}"
            script_dir=$2
            shift 2
            ;;

        --base_dir)
            require_option_value "$1" "${2:-}"
            base_dir=$2
            shift 2
            ;;

        --subject)
            require_option_value "$1" "${2:-}"
            subject=$2
            shift 2
            ;;

        --reg_dir)
            require_option_value "$1" "${2:-}"
            reg_dir=$2
            shift 2
            ;;

        --input_file)
            require_option_value "$1" "${2:-}"
            input_file=$2
            shift 2
            ;;

        --input_dir)
            require_option_value "$1" "${2:-}"
            input_dir=$2
            shift 2
            ;;

        --output_dir)
            require_option_value "$1" "${2:-}"
            output_dir=$2
            shift 2
            ;;

        -h|--help)
            usage
            exit 0
            ;;

        --)
            shift

            if [[ $# -gt 0 ]]; then
                echo "ERROR: Unexpected positional argument(s): $*" >&2
                echo "All inputs must be supplied using named flags." >&2
                echo "" >&2
                usage >&2
                exit 1
            fi
            ;;

        -*)
            echo "ERROR: Unknown option: $1" >&2
            echo "" >&2
            usage >&2
            exit 1
            ;;

        *)
            echo "ERROR: Unexpected positional argument: $1" >&2
            echo "All inputs must be supplied using named flags." >&2
            echo "" >&2
            usage >&2
            exit 1
            ;;

    esac

done


# =============================================================================
# Check required arguments
# =============================================================================

missing_arguments=()

[[ -z "$script_dir" ]] && missing_arguments+=("--script_dir")
[[ -z "$base_dir" ]]   && missing_arguments+=("--base_dir")
[[ -z "$subject" ]]    && missing_arguments+=("--subject")
[[ -z "$reg_dir" ]]    && missing_arguments+=("--reg_dir")

if [[ ${#missing_arguments[@]} -gt 0 ]]; then

    echo "ERROR: Missing required argument(s):" >&2

    for argument in "${missing_arguments[@]}"; do
        echo "  $argument" >&2
    done

    echo "" >&2
    usage >&2
    exit 1

fi


# =============================================================================
# Convert supplied directory paths to full absolute paths
# =============================================================================

script_dir=$(resolve_path "$script_dir")
base_dir=$(resolve_path "$base_dir")

if [[ -n "$input_dir" ]]; then
    input_dir=$(resolve_path "$input_dir")
fi

if [[ -n "$output_dir" ]]; then
    output_dir=$(resolve_path "$output_dir")
fi


# =============================================================================
# Load FSL
# =============================================================================

if command -v module >/dev/null 2>&1; then
    module load fsl/6.0.7.x
else
    echo "WARNING: The 'module' command is unavailable." >&2
    echo "         Assuming FSL is already available." >&2
fi

if ! command -v fslpython >/dev/null 2>&1; then
    echo "ERROR: fslpython was not found after loading FSL." >&2
    exit 1
fi


# =============================================================================
# Define input, registration and output paths
# =============================================================================

data_dir=$(resolve_path "${base_dir}/${subject}/data")


# A relative registration directory is placed under the subject directory.
if [[ "$reg_dir" = /* ]]; then
    registration_dir=$(resolve_path "$reg_dir")
else
    registration_dir=$(resolve_path "${base_dir}/${subject}/${reg_dir}")
fi


# Use the subject directory as the default output parent directory.
if [[ -n "$output_dir" ]]; then
    output_root="$output_dir"
else
    output_root=$(resolve_path "${base_dir}/${subject}")
fi

out_dir_4xobj=$(resolve_path "${output_root}/4xobj")
out_dir_t2w=$(resolve_path "${output_root}/t2w")


t2w_reference=$(resolve_path "${data_dir}/t2w.nii.gz")
t2w_reference_mask=$(resolve_path "${data_dir}/t2w_mask.nii.gz")
obj4x_reference=$(resolve_path "${data_dir}/4xobj_NeuN.nii.gz")

forward_warp=$(resolve_path \
    "${registration_dir}/source_to_target.img.chain")

reverse_warp=$(resolve_path \
    "${registration_dir}/target_to_source.img.chain")

applywarp_script=$(resolve_path "${script_dir}/applywarp.py")


# =============================================================================
# Check required directories and files
# =============================================================================

echo ""

if [[ ! -d "$base_dir" ]]; then
    echo "ERROR: Base directory not found:" >&2
    echo "  $base_dir" >&2
    exit 1
fi

if [[ ! -d "$script_dir" ]]; then
    echo "ERROR: Script directory not found:" >&2
    echo "  $script_dir" >&2
    exit 1
fi

if [[ ! -d "$data_dir" ]]; then
    echo "ERROR: Subject data directory not found:" >&2
    echo "  $data_dir" >&2
    exit 1
fi

if [[ ! -d "$registration_dir" ]]; then
    echo "ERROR: Registration directory not found:" >&2
    echo "  $registration_dir" >&2
    exit 1
fi

if [[ ! -f "$applywarp_script" ]]; then
    echo "ERROR: applywarp.py not found:" >&2
    echo "  $applywarp_script" >&2
    exit 1
fi

if [[ ! -f "$t2w_reference" ]]; then
    echo "ERROR: T2w reference image not found:" >&2
    echo "  $t2w_reference" >&2
    exit 1
fi

if [[ ! -f "$obj4x_reference" ]]; then
    echo "ERROR: 4xobj NeuN reference image not found:" >&2
    echo "  $obj4x_reference" >&2
    exit 1
fi

if [[ ! -f "$forward_warp" ]]; then
    echo "ERROR: Forward warp chain not found:" >&2
    echo "  $forward_warp" >&2
    exit 1
fi

if [[ ! -f "$reverse_warp" ]]; then
    echo "ERROR: Reverse warp chain not found:" >&2
    echo "  $reverse_warp" >&2
    exit 1
fi

if [[ -n "$input_dir" && ! -d "$input_dir" ]]; then
    echo "ERROR: Supplied input directory not found:" >&2
    echo "  $input_dir" >&2
    exit 1
fi


# =============================================================================
# Determine which files should be processed
# =============================================================================

expected_files=(
    "4xobj_NeuN.nii.gz"
    "4xobj_GFAP.nii.gz"
    "NeuN_map.nii.gz"
    "NeuN_map_density.nii.gz"
    "GFAP_map.nii.gz"
)

input_files=()


if [[ -n "$input_file" && -z "$input_dir" ]]; then

    # Process one file from the default subject data directory.
    input_files+=(
        "$(resolve_path "${data_dir}/${input_file}")"
    )


elif [[ -n "$input_file" && -n "$input_dir" ]]; then

    # Process one file from the supplied input directory.
    input_files+=(
        "$(resolve_path "${input_dir}/${input_file}")"
    )


elif [[ -z "$input_file" && -n "$input_dir" ]]; then

    # Process every .nii.gz file directly inside the supplied directory.
    while IFS= read -r -d '' input_path; do
        input_files+=(
            "$(resolve_path "$input_path")"
        )
    done < <(
        find "$input_dir" \
            -maxdepth 1 \
            -type f \
            -name "*.nii.gz" \
            -print0 |
        sort -z
    )

    if [[ ${#input_files[@]} -eq 0 ]]; then
        echo "ERROR: No .nii.gz files found in:" >&2
        echo "  $input_dir" >&2
        exit 1
    fi


else

    # Process the four files with the expected names.
    for expected_file in "${expected_files[@]}"; do
        input_files+=(
            "$(resolve_path "${data_dir}/${expected_file}")"
        )
    done

fi


# =============================================================================
# Check explicitly selected input file
# =============================================================================

# If the user explicitly selects one file, a missing file is an error.
# When using the default list, missing files are skipped with a warning.

if [[ -n "$input_file" ]]; then

    selected_input="${input_files[0]}"

    if [[ ! -f "$selected_input" ]]; then
        echo "ERROR: Selected input file not found:" >&2
        echo "  $selected_input" >&2
        exit 1
    fi

    if [[ "$selected_input" != *.nii.gz ]]; then
        echo "ERROR: Selected input must end in .nii.gz:" >&2
        echo "  $selected_input" >&2
        exit 1
    fi

fi


# =============================================================================
# Create output directories
# =============================================================================

mkdir -p "$out_dir_4xobj"
mkdir -p "$out_dir_t2w"


# =============================================================================
# Helper function: apply forward warp from 4xobj to T2w
# =============================================================================

apply_to_t2w()
{
    local input_path=$1
    local input_name
    local stem
    local output_path

    if [[ ! -f "$input_path" ]]; then
        echo "WARNING: Input file not found; skipping:" >&2
        echo "  $input_path" >&2
        return 0
    fi

    input_name=$(basename "$input_path")

    if [[ "$input_name" != *.nii.gz ]]; then
        echo "WARNING: Input is not a .nii.gz file; skipping:" >&2
        echo "  $input_path" >&2
        return 0
    fi

    stem="${input_name%.nii.gz}"

    output_path=$(resolve_path \
        "${out_dir_t2w}/${stem}_to_t2w_cubic.nii.gz")

    echo "Processing:"
    echo "  Input:        $input_path"
    echo "  Reference:    $t2w_reference"
    echo "  Forward warp: $forward_warp"
    echo "  Output:       $output_path"
    echo ""

    fslpython "$applywarp_script" \
        -i "$input_path" \
        -o "$output_path" \
        -r "$t2w_reference" \
        -w "$forward_warp" \
        --interpolation="cubic"
}


# =============================================================================
# Helper function: copy a source file to the 4xobj output directory
# =============================================================================

copy_to_4xobj_directory()
{
    local input_path=$1
    local input_name
    local destination
    local source_resolved
    local destination_resolved

    if [[ ! -f "$input_path" ]]; then
        echo "WARNING: File not found; cannot copy:" >&2
        echo "  $input_path" >&2
        return 0
    fi

    input_name=$(basename "$input_path")
    destination=$(resolve_path "${out_dir_4xobj}/${input_name}")

    source_resolved=$(resolve_path "$input_path")
    destination_resolved=$(resolve_path "$destination")

    if [[ "$source_resolved" == "$destination_resolved" ]]; then
        echo "File is already in the 4xobj output directory:"
        echo "  $input_path"
        return 0
    fi

    echo "Copying original 4xobj-space file:"
    echo "  From: $input_path"
    echo "  To:   $destination"

    cp -f "$input_path" "$destination"
}


# =============================================================================
# Display configuration
# =============================================================================

echo "Configuration"
echo "============="
echo "Subject:                 $subject"
echo "Base directory:          $base_dir"
echo "Script directory:        $script_dir"
echo "Subject data directory:  $data_dir"
echo "Registration directory:  $registration_dir"
echo "Output parent directory: $output_root"
echo "T2w output directory:    $out_dir_t2w"
echo "4xobj output directory:  $out_dir_4xobj"
echo ""

echo "Selected 4xobj-space input files:"

for input_path in "${input_files[@]}"; do
    echo "  $input_path"
done

echo ""


# =============================================================================
# Apply forward warp: 4xobj --> T2w
# =============================================================================

echo "Applying forward warp: 4xobj --> T2w"
echo "====================================="
echo ""

processed_count=0
skipped_count=0

for input_path in "${input_files[@]}"; do

    if [[ -f "$input_path" ]]; then
        apply_to_t2w "$input_path"
        ((processed_count += 1))
    else
        echo "WARNING: Input file not found; skipping:" >&2
        echo "  $input_path" >&2
        ((skipped_count += 1))
    fi

    echo ""

done

if [[ $processed_count -eq 0 ]]; then
    echo "ERROR: None of the selected 4xobj-space files could be processed." >&2
    exit 1
fi


# =============================================================================
# Apply reverse warp: T2w --> 4xobj
# =============================================================================

echo "Applying reverse warp: T2w --> 4xobj"
echo "====================================="
echo ""

t2w_to_4xobj=$(resolve_path \
    "${out_dir_4xobj}/t2w_to_4xobj.nii.gz")

echo "Processing:"
echo "  Input:        $t2w_reference"
echo "  Reference:    $obj4x_reference"
echo "  Reverse warp: $reverse_warp"
echo "  Output:       $t2w_to_4xobj"
echo ""

fslpython "$applywarp_script" \
    -i "$t2w_reference" \
    -o "$t2w_to_4xobj" \
    -r "$obj4x_reference" \
    -w "$reverse_warp" \
    --interpolation="cubic"

echo ""

t2w_to_4xobj_mask=$(resolve_path \
    "${out_dir_4xobj}/t2w_to_4xobj_mask.nii.gz")

echo "Processing:"
echo "  Input:        $t2w_reference_mask"
echo "  Reference:    $obj4x_reference"
echo "  Reverse warp: $reverse_warp"
echo "  Output:       $t2w_to_4xobj_mask"
echo ""

fslpython "$applywarp_script" \
    -i "$t2w_reference_mask" \
    -o "$t2w_to_4xobj_mask" \
    -r "$obj4x_reference" \
    -w "$reverse_warp" \
    --interpolation="nearest"

echo ""


# =============================================================================
# Copy original files into their corresponding space directories
# =============================================================================

echo "Copying original 4xobj-space files"
echo "=================================="
echo ""

for input_path in "${input_files[@]}"; do

    if [[ -f "$input_path" ]]; then
        copy_to_4xobj_directory "$input_path"
        echo ""
    fi

done


echo "Copying original T2w image"
echo "=========================="
echo ""

t2w_copy=$(resolve_path "${out_dir_t2w}/t2w.nii.gz")
t2w_copy_mask=$(resolve_path "${out_dir_t2w}/t2w_mask.nii.gz")

if [[ "$(resolve_path "$t2w_reference")" != \
      "$(resolve_path "$t2w_copy")" ]]; then

    echo "Copying:"
    echo "  From: $t2w_reference"
    echo "  To:   $t2w_copy"

    cp -f "$t2w_reference" "$t2w_copy"

else

    echo "The original T2w image is already in the T2w output directory:"
    echo "  $t2w_reference"

fi

if [[ "$(resolve_path "$t2w_reference_mask")" != \
      "$(resolve_path "$t2w_copy_mask")" ]]; then
    
    echo "Copying:"
    echo "  From: $t2w_reference_mask"
    echo "  To:   $t2w_copy_mask"

    cp -f "$t2w_reference_mask" "$t2w_copy_mask"

else

    echo "The original T2w image mask is already in the T2w output directory:"
    echo "  $t2w_reference_mask"

fi


# =============================================================================
# Completion message
# =============================================================================

echo ""
echo "Completed"
echo "========="
echo ""
echo "Successfully processed 4xobj-space files: $processed_count"
echo "Skipped missing files:                    $skipped_count"
echo ""
echo "Data in T2w space:"
echo "  $out_dir_t2w"
echo ""
echo "Data in 4xobj space:"
echo "  $out_dir_4xobj"
echo ""
