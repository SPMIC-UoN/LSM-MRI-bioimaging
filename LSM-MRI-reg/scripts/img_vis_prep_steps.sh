#!/usr/bin/env bash

###############################################################################
# Prepare processed LSM and T2w images for visual comparison.
#
# The script thresholds previously stitched NIfTI comparisons, overlays the
# subject-specific voted atlas, and creates sagittal, coronal, and axial GIFs.
#
# Author: Stephania Assimopoulos
###############################################################################

usage() {
    cat <<'EOF'
Usage:
  img_vis_prep_steps_polished.sh [OPTIONS]

Required options:
  --scripts_dir DIR    Directory containing the supporting scripts.
  --base_dir DIR       Base processing directory.
  --subject ID         Subject identifier.
  --space NAME         Image space to process (for example, 4xobj or t2w).
  --slice VALUE        Slice location passed to slicer for all orientations.
  --threshold MODE     Thresholding mode:
                         prc  Use the 5th and 95th percentiles.
                         man  Use fixed values of 0.13 and 1.14.

Other options:
  --mask FILE          Mask used for masking and intensity normalisation.
                       Default: BASE_DIR/SUBJECT/data/SPACE_mask.nii.gz
  --overwrite          Recreate outputs even when they already exist.
                       By default, existing outputs are skipped.
  -h, --help           Show this help message and exit.

Example:
  ./img_vis_prep_steps_polished.sh \
      --scripts_dir /path/to/scripts \
      --base_dir /path/to/processing \
      --subject TAGL_2p4e \
      --space 4xobj \
      --slice 0.5 \
      --threshold prc \
      --mask /path/to/custom_mask.nii.gz \
      --overwrite
EOF
}

die() {
    echo "ERROR: $*" >&2
    echo "Run '$0 --help' for usage information." >&2
    exit 1
}

print_step() {
    printf '\n[%s/6] %s\n' "$1" "$2"
}

should_generate() {
    local output_file="$1"

    if [[ "$overwrite" == true ]]; then
        if [[ -f "$output_file" ]]; then
            echo "      Overwriting: $output_file"
        fi
        return 0
    fi

    if [[ -f "$output_file" ]]; then
        echo "      Skipping existing: $output_file"
        return 1
    fi

    return 0
}

is_mask_image() {
    local image_path="$1"
    local image_name
    local selected_mask_name
    local selected_mask_stem

    image_path=$(realpath -m "$image_path")
    image_name=$(basename "$image_path")
    selected_mask_name=$(basename "$mask")
    selected_mask_stem="${selected_mask_name%.nii.gz}"

    # Always exclude the mask selected for this run. Also exclude masks that
    # follow the pipeline's standard naming convention, plus any downstream
    # derivatives that may have been produced by an earlier run.
    [[ "$image_path" == "$mask" ]] && return 0
    [[ "$image_name" == "${selected_mask_stem}_"* ]] && return 0
    [[ "$image_name" == *_mask.nii.gz ]] && return 0
    [[ "$image_name" == *_mask_* ]] && return 0

    return 1
}

scripts_dir=""
base_dir=""
subject=""
space=""
slice=""
thresh=""
mask=""
overwrite=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --scripts_dir)
            [[ $# -ge 2 ]] || die "Missing value for --scripts_dir."
            scripts_dir="$2"
            shift 2
            ;;
        --base_dir)
            [[ $# -ge 2 ]] || die "Missing value for --base_dir."
            base_dir="$2"
            shift 2
            ;;
        --subject)
            [[ $# -ge 2 ]] || die "Missing value for --subject."
            subject="$2"
            shift 2
            ;;
        --space)
            [[ $# -ge 2 ]] || die "Missing value for --space."
            space="$2"
            shift 2
            ;;
        --slice)
            [[ $# -ge 2 ]] || die "Missing value for --slice."
            slice="$2"
            shift 2
            ;;
        --threshold)
            [[ $# -ge 2 ]] || die "Missing value for --threshold."
            thresh="$2"
            shift 2
            ;;
        --mask)
            [[ $# -ge 2 ]] || die "Missing value for --mask."
            mask="$2"
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
            die "Unknown option: $1"
            ;;
    esac
done

[[ -n "$scripts_dir" ]] || die "--scripts_dir is required."
[[ -n "$base_dir" ]]    || die "--base_dir is required."
[[ -n "$subject" ]]     || die "--subject is required."
[[ -n "$space" ]]       || die "--space is required."
[[ -n "$slice" ]]       || die "--slice is required."
[[ -n "$thresh" ]]      || die "--threshold is required."

[[ "$thresh" == "prc" || "$thresh" == "man" ]] \
    || die "--threshold must be either 'prc' or 'man'."

# Resolve paths before displaying or using them. This ensures that relative
# inputs such as "./." are shown as complete absolute paths.
scripts_dir=$(realpath -m "$scripts_dir")
base_dir=$(realpath -m "$base_dir")

if [[ -n "$mask" ]]; then
    mask=$(realpath -m "$mask")
else
    mask="${base_dir}/${subject}/data/${space}_mask.nii.gz"
fi

module load fsl/6.0.7.x
shopt -s nullglob

printf '\n============================================================\n'
printf ' Image visualisation preparation\n'
printf '============================================================\n'
printf 'Subject:          %s\n' "$subject"
printf 'Space:            %s\n' "$space"
printf 'Slice:            %s\n' "$slice"
printf 'Threshold mode:   %s\n' "$thresh"
printf 'Existing outputs: %s\n' "$([[ "$overwrite" == true ]] && echo "overwrite" || echo "skip")"
printf 'Mask:             %s\n' "$mask"
printf 'Base directory:   %s\n' "$base_dir"
printf 'Scripts directory:%s\n' " $scripts_dir"

###############################################################################
# Step 1: Create masked versions of the LSM images (if not present).
###############################################################################

print_step 1 "Mask LSM images"

step1_images=("${base_dir}/${subject}/${space}"/*.nii.gz)

for img in "${step1_images[@]}"; do
    if is_mask_image "$img"; then
        echo "      Skipping mask input: $img"
        continue
    fi

    # Masked files are outputs of this step, not new inputs on subsequent runs.
    [[ "$img" == *_masked.nii.gz ]] && continue

    output="${img%.nii.gz}_masked.nii.gz"
    if should_generate "$output"; then
        echo "      Processing: $img"
        echo "      Output:     $output"
        fslmaths "$img" -mas "$mask" "$output"
    fi
done

# Example for creating the 4xobj mask:
# fslpython "${scripts_dir}/applywarp.py" \
#     -i "${base_dir}/${subject}/data/t2w_mask.nii.gz" \
#     -w "${base_dir}/${subject}/4xobj_sqrt_to_t2w_direct_AllRegSteps_sqrt_thr250/target_to_source.img.chain" \
#     -r "${base_dir}/${subject}/data/4xobj_NeuN.nii.gz" \
#     --interpolation="nearest" \
#     -o "${base_dir}/${subject}/data/4xobj_mask.nii.gz"
# fslmaths "${base_dir}/${subject}/data/4xobj_mask.nii.gz" \
#     -bin "${base_dir}/${subject}/data/4xobj_mask.nii.gz"

###############################################################################
# Step 2: Normalise intensity of images.
###############################################################################

print_step 2 "Normalise image intensities"

scaled_dir="${base_dir}/${subject}/${space}/scaled_niftys"
mkdir -p "$scaled_dir"

step2_images=(
    "${base_dir}/${subject}/${space}"/*_masked.nii.gz
)

for img in "${step2_images[@]}"; do
    if is_mask_image "$img"; then
        echo "      Skipping mask input: $img"
        continue
    fi

    nm=$(basename "$img")
    output="${scaled_dir}/${nm%.nii.gz}_scaled.nii.gz"

    if should_generate "$output"; then
        echo "      Processing: $img"
        echo "      Output:     $output"
        PLOW=$(fslstats "$img" -P 3.0)
        PHIGH=$(fslstats "$img" -P 92.0)

        # Scientific notation prevents some FSL builds from interpreting a
        # computed decimal scalar as the name of a second image.
        PLOW_SCALAR=$(awk -v value="$PLOW" \
            'BEGIN { printf "%.12e", value }')

        if ! RANGE_SCALAR=$(awk -v low="$PLOW" -v high="$PHIGH" '
            BEGIN {
                range = high - low
                if (range <= 0) {
                    exit 1
                }
                printf "%.12e", range
            }
        '); then
            die "Invalid percentile range for $img (P3=$PLOW, P92=$PHIGH)."
        fi

        echo "      P3:         $PLOW"
        echo "      P92:        $PHIGH"
        echo "      Range:      $(awk -v low="$PLOW" -v high="$PHIGH" \
            'BEGIN { printf "%.6f", high - low }')"

        fslmaths "$img" -sub "$PLOW_SCALAR" -div "$RANGE_SCALAR" \
            -mas "$mask" "$output"
    fi
done

###############################################################################
# Step 3: Split each image along each of the three dimensions.
###############################################################################

print_step 3 "Split images across the midline in x, y, and z"

split_dir="${scaled_dir}/split_niftys"
mkdir -p "$split_dir"

for img in "${scaled_dir}"/*.nii.gz; do
    if is_mask_image "$img"; then
        echo "      Skipping mask derivative: $img"
        continue
    fi

    nm=$(basename "$img" .nii.gz)

    for dim in dim1 dim2 dim3; do
        case "$dim" in
            dim1) split_name="xsplit" ;;
            dim2) split_name="ysplit" ;;
            dim3) split_name="zsplit" ;;
        esac

        output_a="${split_dir}/${nm}_${split_name}_A.nii.gz"
        output_b="${split_dir}/${nm}_${split_name}_B.nii.gz"

        if [[ "$overwrite" == false && -f "$output_a" && -f "$output_b" ]]; then
            echo "      Skipping existing pair:"
            echo "        $output_a"
            echo "        $output_b"
            continue
        fi

        if [[ "$overwrite" == true && ( -f "$output_a" || -f "$output_b" ) ]]; then
            echo "      Overwriting split pair:"
            echo "        $output_a"
            echo "        $output_b"
        else
            echo "      Splitting: $img ($dim)"
        fi
        echo "      Output A:  $output_a"
        echo "      Output B:  $output_b"

        sh "${scripts_dir}/nifti_split_general.sh" "$img" "$split_dir" "$dim"
    done
done

###############################################################################
# Step 4: Stitch the LSM and T2w images across each dimension.
###############################################################################

print_step 4 "Stitch each LSM image with the T2w image in x, y, and z"

out_dir="${base_dir}/${subject}/${space}/scaled_niftys/nifty_comp"
mkdir -p "$out_dir"

for splt in xsplit ysplit zsplit; do
    for img in "${split_dir}"/*_masked_*_"${splt}"_B.nii.gz; do
        if is_mask_image "$img"; then
            echo "      Skipping mask derivative: $img"
            continue
        fi

        for t2w in "${split_dir}"/t2w_*masked*_"${splt}"_A.nii.gz; do
            if is_mask_image "$t2w"; then
                echo "      Skipping mask derivative: $t2w"
                continue
            fi

            if [[ ! "$img" =~ t2w ]]; then
                nm=$(basename "$img")
                output="${out_dir}/${nm//_to_t2w/}"
                output="${output//${splt}/vs_t2w_${splt}}"
                output="${output//_B/}"

                if should_generate "$output"; then
                    echo "      LSM input: $img"
                    echo "      T2w input: $t2w"
                    echo "      Output:    $output"
                    fslmaths "$img" -add "$t2w" "$output"
                fi
            fi
        done
    done
done

###############################################################################
# Step 5: Rescale the intensity of the stitched images.
###############################################################################

print_step 5 "Rescale stitched-image intensities for visualisation"

if [[ "$thresh" == "prc" ]]; then
    echo "      Using the 5th and 95th percentile values."
    out_dir="${base_dir}/${subject}/${space}/scaled_niftys/nifty_comp/thresholded/prc_thresh"
    mkdir -p "$out_dir"

    for img in "${base_dir}/${subject}/${space}/scaled_niftys/nifty_comp"/*_vs_*.nii.gz; do
        if is_mask_image "$img"; then
            echo "      Skipping mask derivative: $img"
            continue
        fi

        nm=$(basename "${img//.nii.gz/}")
        output="${out_dir}/${nm%.nii.gz}_PRCthr.nii.gz"

        if should_generate "$output"; then
            echo "      Processing: $img"
            echo "      Output:     $output"
            PHIGH=$(fslstats "$img" -P 95.0)
            PLOW=$(fslstats "$img" -P 5.0)

            if ! read -r PLOW_SCALAR PHIGH_SCALAR < <(
                awk -v low="$PLOW" -v high="$PHIGH" '
                    BEGIN {
                        if (high <= low) {
                            exit 1
                        }
                        printf "%.12e %.12e\n", low, high
                    }
                '
            ); then
                die "Invalid percentile thresholds for $img (P5=$PLOW, P95=$PHIGH)."
            fi

            echo "      P5:         $PLOW"
            echo "      P95:        $PHIGH"

            fslmaths "$img" \
                -thr "$PLOW_SCALAR" \
                -min "$PHIGH_SCALAR" \
                "$output"
        fi
    done
fi

if [[ "$thresh" == "man" ]]; then
    echo "      Using manually fixed values: 0.13 to 1.14."
    out_dir="${base_dir}/${subject}/${space}/scaled_niftys/nifty_comp/thresholded/man_thresh"
    mkdir -p "$out_dir"

    for img in "${base_dir}/${subject}/${space}/scaled_niftys/nifty_comp"/*_vs_*.nii.gz; do
        if is_mask_image "$img"; then
            echo "      Skipping mask derivative: $img"
            continue
        fi

        nm=$(basename "${img//.nii.gz/}")
        output="${out_dir}/${nm%.nii.gz}_MANthr.nii.gz"

        if should_generate "$output"; then
            echo "      Processing: $img"
            echo "      Output:     $output"
            fslmaths "$img" \
                -thr 1.300000000000e-01 \
                -min 1.140000000000e+00 \
                "$output"
        fi
    done
fi

###############################################################################
# Step 6: Create cross-section GIFs in each orientation.
###############################################################################

print_step 6 "Overlay the atlas outline and create sagittal, coronal, and axial GIFs"

out_dir="${base_dir}/${subject}/${space}/scaled_niftys/nifty_comp/thresholded/${thresh}_thresh/atlas_overlay"
mkdir -p "$out_dir"

# Include the selected slice in each GIF filename. Replace characters that
# could create invalid or confusing paths while leaving values such as 0.5
# unchanged.
slice_label="${slice//\//-}"
slice_label="${slice_label// /_}"

for img in "${base_dir}/${subject}/${space}/scaled_niftys/nifty_comp/thresholded/${thresh}_thresh"/*.nii.gz; do
    if is_mask_image "$img"; then
        echo "      Skipping mask derivative: $img"
        continue
    fi

    nm=$(basename "$img")

    for atl in "${base_dir}/atlases/${subject}/${space}"/*voted.nii; do
        sag_output="${out_dir}/${nm%.nii.gz}_atl_sag_slice-${slice_label}.gif"
        cor_output="${out_dir}/${nm%.nii.gz}_atl_cor_slice-${slice_label}.gif"
        ax_output="${out_dir}/${nm%.nii.gz}_atl_ax_slice-${slice_label}.gif"

        if should_generate "$sag_output"; then
            echo "      Creating sagittal GIF: $sag_output"
            slicer "$img" "$atl" -x "$slice" "$sag_output"
        fi

        if should_generate "$cor_output"; then
            echo "      Creating coronal GIF: $cor_output"
            slicer "$img" "$atl" -y "$slice" "$cor_output"
        fi

        if should_generate "$ax_output"; then
            echo "      Creating axial GIF: $ax_output"
            slicer "$img" "$atl" -z "$slice" "$ax_output"
        fi
    done
done

printf '\n============================================================\n'
printf ' Complete\n'
printf '============================================================\n'
printf 'GIF output directory:\n%s\n' "$out_dir"
printf 'All images are ready to be assembled into a figure.\n\n'
