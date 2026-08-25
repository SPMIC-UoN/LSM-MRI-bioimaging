#!/usr/bin/env fslpython
"""
Create one registration montage per subject.

Rows    = stains / contrasts
Columns = orientations
Title   = subject name

Important behaviour:
- Each image is cropped around the actual brain content.
- The crop box is shared within each orientation, across all stains for that subject.
  This keeps rows comparable and prevents one row being zoomed differently.
- Columns are allowed to have different widths, so sagittal images are not cut off.
- Optional per-orientation display scaling lets you reduce sagittal/coronal size
  without changing row-to-row scale within that orientation.
- The GIF search folder can be prescribed with --input_subdir.
- GIFs are found recursively at any depth below the search folder.
- Filename pattern groups can be added to or replaced from the command line.
"""

from pathlib import Path
from PIL import Image, ImageSequence, ImageDraw, ImageFont
import argparse
import numpy as np
import re

try:
    from scipy import ndimage as ndi
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False


# ----------------------------
# File matching
# ----------------------------

def filename_tokens(path):
    """Return lowercase alphanumeric tokens from a filename."""
    return {
        token
        for token in re.split(r"[^a-zA-Z0-9]+", path.stem.lower())
        if token
    }


def normalise_token(value):
    """Lowercase a value and remove non-alphanumeric separators."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def path_matches_threshold(path, threshold):
    """Check threshold directory names, ignoring case and separators."""
    if threshold is None:
        return True

    wanted = f"{threshold}thresh"
    parent_parts = [normalise_token(part) for part in path.parent.parts]
    return any(wanted in part for part in parent_parts)


def filename_matches_slice(path, requested_slice):
    """
    Match slice-<number> anywhere in a filename.

    Values are compared numerically, so slice-0.5 and slice-0.50 are equivalent.
    """
    if requested_slice is None:
        return True

    slice_pattern = re.compile(
        r"(?:^|[^a-zA-Z0-9])slice[-_]?"
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))"
        r"(?:$|[^0-9.])",
        flags=re.IGNORECASE,
    )
    for match in slice_pattern.finditer(path.stem):
        if abs(float(match.group(1)) - requested_slice) <= 1e-9:
            return True
    return False


def find_match(
    folder,
    patterns,
    orientation,
    split,
    threshold=None,
    requested_slice=None,
):
    """
    Recursively match contrast patterns plus exact orientation/split tokens.

    The orientation and split may occur anywhere in the filename.
    """
    orientation = orientation.lower()
    split = split.lower()

    for pattern in patterns:
        matches = [
            path
            for path in sorted(folder.rglob(pattern))
            if orientation in filename_tokens(path)
            and split in filename_tokens(path)
            and path_matches_threshold(path, threshold)
            and filename_matches_slice(path, requested_slice)
        ]
        if matches:
            return matches[0], matches
    return None, []


def format_template(template, *, subject, space, orientation=None, split=None):
    """Format supported placeholders and report misspelled placeholders clearly."""
    values = {
        "subject": subject,
        "space": space,
        "orientation": orientation if orientation is not None else "{orientation}",
        "split": split if split is not None else "{split}",
    }
    try:
        return template.format(**values)
    except KeyError as exc:
        supported = ", ".join(f"{{{key}}}" for key in values)
        raise ValueError(
            f"Unknown placeholder {exc} in '{template}'. "
            f"Supported placeholders are: {supported}"
        ) from exc


def parse_pattern_args(pattern_args):
    """
    Parse repeatable LABEL=GLOB definitions.

    Repeating a label supplies fallback patterns for that same montage row:
      --pattern 'NeuN=NeuN*{orientation}*.gif'
                'NeuN=NeuN_alt*{orientation}*.gif'
    """
    parsed = {}
    for item in pattern_args or []:
        if "=" not in item:
            raise ValueError(
                f"Invalid --pattern entry '{item}'. "
                "Use LABEL=GLOB, e.g. 'NeuN=NeuN*{orientation}*.gif'"
            )
        label, pattern = item.split("=", 1)
        label = label.strip()
        pattern = pattern.strip()
        if not label or not pattern:
            raise ValueError(
                f"Invalid --pattern entry '{item}': both LABEL and GLOB are required."
            )
        parsed.setdefault(label, []).append(pattern)
    return parsed


def normalise_split(split):
    """Convert x/y/z or xsplit/ysplit/zsplit to the filename token."""
    split = split.lower().strip()
    aliases = {
        "x": "xsplit",
        "y": "ysplit",
        "z": "zsplit",
        "xsplit": "xsplit",
        "ysplit": "ysplit",
        "zsplit": "zsplit",
    }
    if split not in aliases:
        raise ValueError(
            f"Invalid split '{split}'. Use x, y, z, xsplit, ysplit, or zsplit."
        )
    return aliases[split]


def slice_filename_tag(slice_value):
    """Return a compact filename tag such as 'slice-0.5', or None."""
    if slice_value is None:
        return None
    return f"slice-{slice_value:g}"


def slices_filename_tag(orientations, slice_values):
    """Build a concise output tag for one or several orientation slices."""
    if not slice_values:
        return None

    if all(abs(value - slice_values[0]) <= 1e-9 for value in slice_values[1:]):
        return slice_filename_tag(slice_values[0])

    mapping = "_".join(
        f"{orientation}-{value:g}"
        for orientation, value in zip(orientations, slice_values)
    )
    return f"slices-{mapping}"


def load_first_frame(gif_path):
    im = Image.open(gif_path)
    frame = next(ImageSequence.Iterator(im)).convert("RGB")
    return frame


# ----------------------------
# Cropping utilities
# ----------------------------

def bbox_from_mask(mask):
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def expand_bbox(bbox, im_w, im_h, pad_px=20, pad_frac=0.04):
    left, top, right, bottom = bbox
    bw = right - left
    bh = bottom - top
    pad = max(int(pad_px), int(round(max(bw, bh) * pad_frac)))
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(im_w, right + pad)
    bottom = min(im_h, bottom + pad)
    return left, top, right, bottom


def content_bbox(
    im,
    black_threshold=25,
    min_component_area=800,
    crop_padding_px=30,
    crop_padding_frac=0.04,
):
    """
    Estimate bbox around the main non-black content.

    This deliberately ignores tiny components, e.g. R/L orientation letters,
    isolated text fragments, and single-pixel noise. If scipy is available,
    connected components are used. If not, it falls back to a simple threshold
    bbox.
    """
    arr = np.asarray(im.convert("RGB"))

    # Any channel above threshold counts as content.
    # This captures both greyscale tissue and red outlines.
    mask = arr.max(axis=2) > black_threshold

    if not mask.any():
        return (0, 0, im.width, im.height)

    if HAVE_SCIPY:
        # Light closing/filling makes thin red contours and grayscale tissue
        # behave as a single anatomical object more often.
        mask2 = ndi.binary_closing(mask, structure=np.ones((5, 5)))
        mask2 = ndi.binary_fill_holes(mask2)

        lab, nlab = ndi.label(mask2)
        if nlab > 0:
            areas = np.bincount(lab.ravel())
            areas[0] = 0

            keep = np.zeros_like(mask2, dtype=bool)
            for lab_id, area in enumerate(areas):
                if lab_id == 0:
                    continue
                if area >= min_component_area:
                    keep |= (lab == lab_id)

            # If the threshold was too strict and nothing survived,
            # keep the largest component rather than cropping the whole image.
            if not keep.any():
                largest = int(np.argmax(areas))
                keep = lab == largest

            bbox = bbox_from_mask(keep)
        else:
            bbox = bbox_from_mask(mask)
    else:
        bbox = bbox_from_mask(mask)

    if bbox is None:
        bbox = (0, 0, im.width, im.height)

    return expand_bbox(
        bbox,
        im.width,
        im.height,
        pad_px=crop_padding_px,
        pad_frac=crop_padding_frac,
    )


def union_bboxes(bboxes):
    bboxes = [b for b in bboxes if b is not None]
    if not bboxes:
        return None
    left = min(b[0] for b in bboxes)
    top = min(b[1] for b in bboxes)
    right = max(b[2] for b in bboxes)
    bottom = max(b[3] for b in bboxes)
    return left, top, right, bottom


def resize_keep_aspect(im, target_h):
    scale = target_h / im.height
    target_w = max(1, int(round(im.width * scale)))
    return im.resize((target_w, target_h), Image.Resampling.LANCZOS)


def make_font(size):
    for font_name in ["Arial Bold.ttf", "Arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def parse_orientation_scales(scale_args):
    """
    Parse items like:
      axial=1 coronal=1 sagittal=0.85
      xsplit_atlas_ax=1 ysplit_atlas_sag=0.75
      0=1 1=1 2=0.75

    Keys are case-insensitive. Exact orientation-string matches are used first.
    Then aliases are tried, so axial also applies to names containing ax,
    coronal to names containing cor, and sagittal to names containing sag.
    """
    scales = {}
    for item in scale_args or []:
        if "=" not in item:
            raise ValueError(
                f"Invalid --orientation_scales entry '{item}'. Use orientation=value, e.g. sagittal=0.85"
            )
        key, value = item.split("=", 1)
        key = key.strip().lower()
        try:
            value = float(value)
        except ValueError as exc:
            raise ValueError(f"Invalid scale value in '{item}'") from exc
        if value <= 0:
            raise ValueError(f"Scale must be > 0 in '{item}'")
        scales[key] = value
    return scales


def orientation_aliases(orientation):
    """Return aliases for an orientation filename token."""
    o = orientation.lower()
    aliases = [o]

    # Your filenames use e.g. xsplit_atlas_ax, xsplit_atlas_cor, ysplit_atlas_sag.
    # These should respond to intuitive scale keys: axial/coronal/sagittal.
    parts = [p for p in o.replace("-", "_").split("_") if p]

    if "ax" in parts or o.endswith("ax") or "axial" in o:
        aliases += ["axial", "ax"]
    if "cor" in parts or o.endswith("cor") or "coronal" in o:
        aliases += ["coronal", "cor"]
    if "sag" in parts or o.endswith("sag") or "sagittal" in o:
        aliases += ["sagittal", "sag"]

    return aliases


def scale_for_orientation(orientation_scales, orientation, column_index):
    """Find scale by exact key, alias, or column number."""
    if not orientation_scales:
        return 1.0

    # Column-index keys are useful when orientation names are long.
    # Accept both 0-based and 1-based column numbering.
    for key in (str(column_index), str(column_index + 1)):
        if key in orientation_scales:
            return orientation_scales[key]

    for key in orientation_aliases(orientation):
        if key in orientation_scales:
            return orientation_scales[key]

    return 1.0


# ----------------------------
# Arguments
# ----------------------------

parser = argparse.ArgumentParser()

parser.add_argument("--base_dir", required=True)
parser.add_argument("--space", required=True)
parser.add_argument("--out_dir", required=True)

parser.add_argument(
    "--input_subdir",
    default="{space}",
    help=(
        "Recursive search root relative to each subject directory. The placeholders "
        "{subject} and {space} are supported. Default: '{space}', giving "
        "BASE_DIR/SUBJECT/SPACE. Every directory below this root is searched, "
        "so intermediate directory names do not need to be supplied. "
        "An absolute path is also accepted."
    ),
)

parser.add_argument(
    "--pattern",
    action="append",
    nargs="+",
    default=None,
    metavar="LABEL=GLOB",
    help=(
        "Add filename glob(s), grouped by montage row label. May be repeated, "
        "and each use may contain multiple quoted LABEL=GLOB entries. Patterns "
        "are applied recursively. Orientation and split are checked separately "
        "as exact filename tokens, wherever they occur. The placeholders "
        "{orientation}, {split}, {subject}, and {space} remain available. "
        "By default these are added to the built-in groups. "
        "Example: --pattern 'NeuN=NeuN*.gif'"
    ),
)

parser.add_argument(
    "--replace_default_patterns",
    action="store_true",
    help=(
        "Use only groups supplied with --pattern. Without this flag, a supplied "
        "label replaces that built-in label's patterns, while new labels are added."
    ),
)

parser.add_argument(
    "--subjects",
    nargs="*",
    default=None,
    help="Optional list of subjects. If omitted, all subdirectories under base_dir are used.",
)

parser.add_argument(
    "--orientations",
    nargs="+",
    default=["ax", "cor", "sag"],
    help=(
        "Filename orientation tokens to use as columns, in order. "
        "Default: ax cor sag."
    ),
)

parser.add_argument(
    "--split",
    nargs="+",
    required=True,
    metavar="SPLIT",
    help=(
        "One split per orientation, in the same order as --orientations. "
        "Each value may be x, y, z, xsplit, ysplit, or zsplit. "
        "Example: --orientations ax cor sag --split x y z."
    ),
)

parser.add_argument(
    "--threshold",
    choices=["prc", "man"],
    default=None,
    help=(
        "Optional threshold-directory filter. 'prc' keeps GIFs below a "
        "PRCthresh/prc_thresh directory; 'man' keeps GIFs below a "
        "MANthresh/man_thresh directory. Omit when no disambiguation is needed."
    ),
)

parser.add_argument(
    "--slice",
    type=float,
    nargs="+",
    default=None,
    dest="slice_values",
    metavar="SLICE",
    help=(
        "Optional slice-value filters, with one value per orientation and in "
        "the same order. For example: --orientations ax cor sag "
        "--slice 0.5 0.4 0.6. Each value matches a numeric 'slice-<value>' "
        "field anywhere in the corresponding GIF filename."
    ),
)

parser.add_argument(
    "--padding",
    type=int,
    default=30,
    help="Padding between image tiles, in pixels.",
)

parser.add_argument(
    "--row_height",
    type=int,
    default=None,
    help=(
        "Base displayed row height. If omitted, the script uses the largest "
        "shared crop height found for that subject. Orientation scales are "
        "applied to this height."
    ),
)

parser.add_argument(
    "--orientation_scales",
    nargs="*",
    default=None,
    help=(
        "Optional per-orientation display scale, e.g. "
        "--orientation_scales axial=1 coronal=1 sagittal=0.8. "
        "Use this when one orientation looks visually too large/small. "
        "Scaling is shared across all stains for that orientation."
    ),
)

parser.add_argument("--font_size", type=int, default=44)
parser.add_argument("--title_font_size", type=int, default=52)
parser.add_argument("--label_left", type=int, default=None)
parser.add_argument("--title_height", type=int, default=None)

parser.add_argument(
    "--black_threshold",
    type=int,
    default=25,
    help="Pixels with max RGB above this value are considered non-black content.",
)

parser.add_argument(
    "--min_component_area",
    type=int,
    default=800,
    help="Small connected components below this area are ignored when estimating crop boxes.",
)

parser.add_argument(
    "--crop_padding_px",
    type=int,
    default=45,
    help="Extra padding added around the estimated brain crop.",
)

parser.add_argument(
    "--crop_padding_frac",
    type=float,
    default=0.06,
    help="Extra crop padding as a fraction of the crop size.",
)

parser.add_argument(
    "--out_suffix",
    default="stains_by_orientation_scaled",
    help="Suffix used in output filenames.",
)

args = parser.parse_args()
orientation_scales = parse_orientation_scales(args.orientation_scales)

if len(args.split) != len(args.orientations):
    parser.error(
        "--split must contain exactly one value for each --orientations entry "
        f"({len(args.orientations)} orientations, {len(args.split)} splits supplied)."
    )

try:
    orientation_splits = [
        normalise_split(split)
        for split in args.split
    ]
except ValueError as exc:
    parser.error(str(exc))

if args.slice_values is not None and len(args.slice_values) != len(args.orientations):
    parser.error(
        "--slice must contain exactly one value for each --orientations entry "
        f"({len(args.orientations)} orientations, "
        f"{len(args.slice_values)} slices supplied)."
    )

orientation_slices = (
    args.slice_values
    if args.slice_values is not None
    else [None] * len(args.orientations)
)

# argparse produces one list per --pattern occurrence because nargs='+' and
# action='append' are combined. Flatten them before parsing.
pattern_args = [
    item
    for pattern_group in (args.pattern or [])
    for item in pattern_group
]
cli_patterns = parse_pattern_args(pattern_args)

if args.replace_default_patterns and not cli_patterns:
    parser.error("--replace_default_patterns requires at least one --pattern.")

base_dir = Path(args.base_dir)
out_arg = Path(args.out_dir)

# Backwards-compatible behaviour:
# - if --out_dir ends in .png/.jpg/etc, treat it as a requested output file path
# - otherwise treat it as a directory and create one PNG per subject
image_suffixes = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
if out_arg.suffix.lower() in image_suffixes:
    out_file_requested = out_arg
    out_dir = out_arg.parent
else:
    out_file_requested = None
    out_dir = out_arg
out_dir.mkdir(parents=True, exist_ok=True)

if args.subjects is None or len(args.subjects) == 0:
    subjects = sorted(d.name for d in base_dir.iterdir() if d.is_dir())
    print("Using all subjects found under base_dir:")
else:
    subjects = args.subjects
    print("Using provided subject list:")

for subject in subjects:
    print(f"  {subject}")


# ----------------------------
# Stain/contrast patterns
# ----------------------------

default_contrast_patterns = {
    "4xobj_NeuN": [
        "4xobj_NeuN*.gif",
    ],
    "4xobj_GFAP": [
        "4xobj_GFAP*.gif",
    ],
    "NeuN_map": [
        "NeuN_map*density*.gif",
    ],
    "GFAP_map": [
        "GFAP_map*.gif",
    ],
}

if args.replace_default_patterns:
    contrast_patterns = cli_patterns
else:
    contrast_patterns = {
        label: list(patterns)
        for label, patterns in default_contrast_patterns.items()
    }
    # A command-line definition with an existing label replaces its defaults.
    # A new label adds a new montage row.
    contrast_patterns.update(cli_patterns)

contrast_labels = list(contrast_patterns)


# ----------------------------
# Main loop: one figure per subject
# ----------------------------

font = make_font(args.font_size)
title_font = make_font(args.title_font_size)

for subject in subjects:
    print(f"\nSubject: {subject}")

    input_subdir = Path(
        format_template(
            args.input_subdir,
            subject=subject,
            space=args.space,
        )
    )
    if input_subdir.is_absolute():
        folder = input_subdir
    else:
        folder = base_dir / subject / input_subdir

    folder = folder.resolve()
    print(f"Search folder: {folder}")
    print(
        "Orientation/split selection: "
        + ", ".join(
            f"{orientation}={split}"
            for orientation, split in zip(args.orientations, orientation_splits)
        )
    )
    print(f"Threshold filter: {args.threshold or 'none'}")
    if args.slice_values is None:
        print("Slice selection: none")
    else:
        print(
            "Slice selection: "
            + ", ".join(
                f"{orientation}={slice_value:g}"
                for orientation, slice_value in zip(
                    args.orientations,
                    orientation_slices,
                )
            )
        )

    if not folder.is_dir():
        print(f"WARNING: search folder does not exist; skipping {subject}.")
        continue

    # images[contrast][orientation] = PIL image or None
    images = {contrast: {} for contrast in contrast_labels}
    missing_requests = []

    for contrast in contrast_labels:
        for orientation, split, slice_value in zip(
            args.orientations,
            orientation_splits,
            orientation_slices,
        ):
            patterns = [
                format_template(
                    pattern,
                    subject=subject,
                    space=args.space,
                    orientation=orientation,
                    split=split,
                )
                for pattern in contrast_patterns[contrast]
            ]
            gif, matches = find_match(
                folder,
                patterns,
                orientation=orientation,
                split=split,
                threshold=args.threshold,
                requested_slice=slice_value,
            )

            if gif is None:
                slice_text = (
                    f"{slice_value:g}" if slice_value is not None else "any"
                )
                threshold_text = args.threshold or "any"
                print(
                    "WARNING: requested GIF not found:\n"
                    f"  subject:     {subject}\n"
                    f"  contrast:    {contrast}\n"
                    f"  orientation: {orientation}\n"
                    f"  split:       {split}\n"
                    f"  slice:       {slice_text}\n"
                    f"  threshold:   {threshold_text}\n"
                    f"  search root: {folder}\n"
                    f"  globs tried: {patterns}"
                )
                missing_requests.append(
                    (contrast, orientation, split, slice_value)
                )
                images[contrast][orientation] = None
            else:
                if len(matches) > 1:
                    print(
                        f"WARNING: {len(matches)} matches for "
                        f"{contrast} | {orientation}; using {gif.name}"
                    )
                print(f"Found: {contrast} | {orientation} | {gif.name}")
                images[contrast][orientation] = load_first_frame(gif)

    available = [
        im
        for contrast in contrast_labels
        for im in images[contrast].values()
        if im is not None
    ]

    if len(available) == 0:
        print(f"WARNING: no images found for {subject}; skipping.")
        continue

    if missing_requests:
        print(
            f"WARNING: {len(missing_requests)} of "
            f"{len(contrast_labels) * len(args.orientations)} requested GIFs "
            f"were not found for {subject}. Missing montage positions will "
            "be left blank."
        )

    # Estimate one shared crop box per orientation, across stains.
    shared_crop = {}

    for orientation in args.orientations:
        boxes = []
        for contrast in contrast_labels:
            im = images[contrast][orientation]
            if im is None:
                continue
            box = content_bbox(
                im,
                black_threshold=args.black_threshold,
                min_component_area=args.min_component_area,
                crop_padding_px=args.crop_padding_px,
                crop_padding_frac=args.crop_padding_frac,
            )
            boxes.append(box)

        shared_crop[orientation] = union_bboxes(boxes)
        print(f"Crop box for {orientation}: {shared_crop[orientation]}")

    # Crop all images using the orientation-specific shared crop.
    cropped = {contrast: {} for contrast in contrast_labels}
    crop_heights = []

    for contrast in contrast_labels:
        for orientation in args.orientations:
            im = images[contrast][orientation]
            box = shared_crop[orientation]
            if im is None or box is None:
                cropped[contrast][orientation] = None
            else:
                cim = im.crop(box)
                cropped[contrast][orientation] = cim
                crop_heights.append(cim.height)

    if not crop_heights:
        print(f"WARNING: no cropped images for {subject}; skipping.")
        continue

    # Base row height. Each orientation can then be scaled relative to this.
    # This fixes the common case where sagittal looks too visually large even
    # after correct cropping. The same orientation scale is used for every stain,
    # so row-to-row comparisons remain fair.
    if args.row_height is None:
        base_row_h = max(crop_heights)
    else:
        base_row_h = args.row_height

    display_h = {}
    for c, orientation in enumerate(args.orientations):
        scale = scale_for_orientation(orientation_scales, orientation, c)
        display_h[orientation] = max(1, int(round(base_row_h * scale)))

    # The actual grid row height is the tallest orientation after scaling.
    row_img_h = max(display_h.values())

    print("Display heights by orientation:")
    for orientation in args.orientations:
        print(f"  {orientation}: {display_h[orientation]} px")

    # Resize while preserving aspect ratio.
    resized = {contrast: {} for contrast in contrast_labels}

    # Determine one column width per orientation after resizing.
    col_widths = []
    for orientation in args.orientations:
        widths = []
        for contrast in contrast_labels:
            im = cropped[contrast][orientation]
            if im is None:
                continue
            rim = resize_keep_aspect(im, display_h[orientation])
            resized[contrast][orientation] = rim
            widths.append(rim.width)

        if widths:
            col_widths.append(max(widths))
        else:
            col_widths.append(display_h[orientation])

    n_rows = len(contrast_labels)
    n_cols = len(args.orientations)
    pad = args.padding

    grid_w = sum(col_widths) + (n_cols - 1) * pad
    grid_h = n_rows * row_img_h + (n_rows - 1) * pad

    label_left = args.label_left
    if label_left is None:
        # Enough for longest stain label.
        longest = max(contrast_labels, key=len)
        bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), longest, font=font)
        label_left = (bbox[2] - bbox[0]) + 60

    title_height = args.title_height
    if title_height is None:
        title_height = int(args.title_font_size * 1.8)

    canvas_w = label_left + grid_w
    canvas_h = title_height + grid_h

    labelled = Image.new("RGB", (canvas_w, canvas_h), "black")
    draw = ImageDraw.Draw(labelled)

    # Title
    draw.text(
        (label_left + grid_w / 2, title_height / 2),
        subject,
        fill="white",
        anchor="mm",
        font=title_font,
    )

    # Paste images and row labels.
    y0_grid = title_height

    for r, contrast in enumerate(contrast_labels):
        y_top = y0_grid + r * (row_img_h + pad)
        y_mid = y_top + row_img_h / 2

        draw.text(
            (label_left / 2, y_mid),
            contrast,
            fill="white",
            anchor="mm",
            font=font,
        )

        x_left = label_left
        for c, orientation in enumerate(args.orientations):
            col_w = col_widths[c]
            rim = resized[contrast].get(orientation)

            if rim is not None:
                # Centre each image inside its orientation column.
                x = x_left + (col_w - rim.width) // 2
                y = y_top + (row_img_h - rim.height) // 2
                labelled.paste(rim, (x, y))

            x_left += col_w + pad

    if out_file_requested is not None:
        if len(subjects) == 1:
            out_path = out_file_requested
        else:
            out_path = out_file_requested.with_name(
                f"{out_file_requested.stem}_{subject}{out_file_requested.suffix}"
            )
    else:
        out_path = out_dir / f"{subject}_{args.out_suffix}.png"

    output_tags = []
    if args.threshold is not None:
        output_tags.append(args.threshold)

    slice_tag = slices_filename_tag(args.orientations, args.slice_values)
    if slice_tag is not None:
        output_tags.append(slice_tag)

    if output_tags:
        out_path = out_path.with_name(
            f"{out_path.stem}_{'_'.join(output_tags)}{out_path.suffix}"
        )

    labelled.save(out_path)
    print(f"Saved: {out_path}")
