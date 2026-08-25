#!/usr/bin/env python3
"""
Create a subject-by-contrast PNG for one orientation, split, and slice.

Each row represents one subject and each column represents one contrast. GIFs
are discovered recursively below each subject/space directory.

Author: Stephania Assimopoulos
"""

from __future__ import annotations

import argparse
import re
import sys
import warnings
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


ORIENTATION_ALIASES = {
    "ax": "ax",
    "axial": "ax",
    "cor": "cor",
    "coronal": "cor",
    "sag": "sag",
    "sagittal": "sag",
}

SPLIT_ALIASES = {
    "x": "xsplit",
    "xsplit": "xsplit",
    "y": "ysplit",
    "ysplit": "ysplit",
    "z": "zsplit",
    "zsplit": "zsplit",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a PNG in which rows are subjects and columns are contrasts, "
            "using GIFs from one orientation, split, and slice."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    required = parser.add_argument_group("required arguments")
    required.add_argument(
        "--base-dir",
        "--base_dir",
        dest="base_dir",
        type=Path,
        required=True,
        help="Base directory containing one directory per subject.",
    )
    required.add_argument(
        "--space",
        required=True,
        help="Image space below each subject directory, for example 4xobj or t2w.",
    )
    selection = parser.add_argument_group("input selection")
    selection.add_argument(
        "--contrasts",
        nargs="+",
        help=(
            "Contrast names or unique filename substrings, in the desired "
            "left-to-right column order. If omitted, all matching contrasts "
            "are detected automatically and naturally sorted."
        ),
    )
    required.add_argument(
        "--orientation",
        choices=sorted(ORIENTATION_ALIASES),
        required=True,
        help="Single orientation to include.",
    )
    required.add_argument(
        "--split",
        choices=sorted(SPLIT_ALIASES),
        required=True,
        help="Single split to include.",
    )
    required.add_argument(
        "--slice",
        required=True,
        help="Slice value encoded in the GIF filename, for example 0.5.",
    )

    selection.add_argument(
        "--subjects",
        nargs="+",
        help=(
            "Subject identifiers in row order. If omitted, valid subject "
            "directories are detected automatically and sorted."
        ),
    )
    selection.add_argument(
        "--threshold",
        choices=("prc", "man"),
        help=(
            "Restrict discovery to percentile or manual thresholding. This may "
            "be omitted when only one threshold type matches."
        ),
    )

    layout = parser.add_argument_group("figure layout")
    layout.add_argument(
        "--output-dir",
        "--output_dir",
        dest="output_dir",
        type=Path,
        required=True,
        help=(
            "Directory in which to save the automatically named output PNG."
        ),
    )
    layout.add_argument(
        "--cell-width",
        type=int,
        default=600,
        help="Width in pixels of every contrast cell.",
    )
    layout.add_argument(
        "--cell-height",
        type=int,
        default=450,
        help="Height in pixels of every contrast cell.",
    )
    layout.add_argument(
        "--image-scale",
        type=float,
        default=1.0,
        help=(
            "Scale factor applied to each image after it is fitted inside its "
            "cell. Values above 1 enlarge the image and crop excess borders."
        ),
    )
    layout.add_argument(
        "--scale-mode",
        choices=("normalized", "global"),
        default="normalized",
        help=(
            "'normalized' makes each subject brain fill the same display "
            "region; 'global' preserves pixel-size differences between rows."
        ),
    )
    layout.add_argument("--padding", type=int, default=20)
    layout.add_argument(
        "--font-size",
        type=int,
        default=64,
        help="Font size in pixels for subject and contrast labels.",
    )
    layout.add_argument(
        "--font-file",
        type=Path,
        help=(
            "Optional path to a TrueType/OpenType font. If omitted, the script "
            "searches for a scalable bold font automatically."
        ),
    )
    layout.add_argument(
        "--background",
        choices=("black", "white"),
        default="black",
    )
    layout.add_argument(
        "--autocrop",
        action="store_true",
        help=(
            "Calculate one crop per subject from the first available contrast "
            "and apply it identically to every contrast in that row."
        ),
    )
    layout.add_argument(
        "--crop-threshold",
        type=int,
        default=3,
        help=(
            "Grayscale threshold used when --crop-basis content is selected "
            "or atlas-outline detection is unavailable."
        ),
    )
    layout.add_argument(
        "--crop-basis",
        choices=("t2w", "atlas", "content"),
        default="t2w",
        help=(
            "Feature used to determine the crop. 't2w' uses the stable T2w "
            "half and mirrors its extent around the split; 'atlas' uses the "
            "red outline; 'content' uses grayscale intensity."
        ),
    )
    layout.add_argument(
        "--crop-margin",
        type=int,
        default=0,
        help=(
            "Source-pixel margin restored around the detected crop. Keep at "
            "0 for exact cross-subject normalization; use --image-scale below "
            "1 instead for a consistent display margin."
        ),
    )
    layout.add_argument(
        "--crop-min-content",
        type=float,
        default=0.01,
        help=(
            "Minimum fraction of non-background pixels required to retain a "
            "row or column during autocropping. This removes isolated dots and "
            "lines that would otherwise alter image scale."
        ),
    )

    args = parser.parse_args()

    for name in ("cell_width", "cell_height", "padding", "font_size"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be greater than zero.")
    if args.image_scale <= 0:
        parser.error("--image-scale must be greater than zero.")

    if not 0 <= args.crop_threshold <= 255:
        parser.error("--crop-threshold must be between 0 and 255.")
    if args.crop_margin < 0:
        parser.error("--crop-margin cannot be negative.")
    if not 0 <= args.crop_min_content <= 1:
        parser.error("--crop-min-content must be between 0 and 1.")

    return args


def load_font(
    size: int,
    requested_font: Path | None,
) -> tuple[ImageFont.FreeTypeFont, str]:
    if requested_font is not None:
        font_path = requested_font.expanduser().resolve()
        if not font_path.is_file():
            raise FileNotFoundError(f"Font file does not exist: {font_path}")
        return ImageFont.truetype(str(font_path), size), str(font_path)

    # Pillow can often resolve DejaVu Sans by name even when it is not in one
    # of the usual system font directories.
    font_names = (
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
        "Arial Bold.ttf",
    )
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size), font_name
        except OSError:
            pass

    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/local/share/fonts/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size), candidate

    search_roots = (
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    )
    preferred_patterns = (
        "*Sans*Bold*.ttf",
        "*Sans*Bold*.otf",
        "*.ttf",
        "*.otf",
    )
    for root in search_roots:
        if not root.is_dir():
            continue
        for pattern in preferred_patterns:
            matches = sorted(root.rglob(pattern))
            if matches:
                font_path = matches[0]
                return ImageFont.truetype(str(font_path), size), str(font_path)

    raise FileNotFoundError(
        "No scalable TrueType/OpenType font could be found. Supply one with "
        "--font-file /full/path/to/font.ttf. The script will not use Pillow's "
        "fixed-size fallback because it ignores --font-size."
    )


def normalize_slice(value: str) -> str:
    """Return a stable textual slice representation for matching and naming."""
    try:
        return f"{float(value):g}"
    except ValueError:
        return value.strip()


def threshold_type(path: Path) -> str | None:
    text = str(path).lower()
    name = path.name.lower()
    if "prcthr" in name or "prc_thresh" in text or "prcthresh" in text:
        return "prc"
    if "manthr" in name or "man_thresh" in text or "manthresh" in text:
        return "man"
    return None


def slice_matches(filename: str, requested_slice: str) -> bool:
    patterns = (
        rf"(?:^|[_-])slice[-_]?{re.escape(requested_slice)}(?:[_\-.]|$)",
        rf"(?:^|[_-])slc[-_]?{re.escape(requested_slice)}(?:[_\-.]|$)",
    )
    return any(re.search(pattern, filename, flags=re.IGNORECASE) for pattern in patterns)


def discover_subjects(base_dir: Path, space: str) -> list[str]:
    subjects = sorted(
        entry.name
        for entry in base_dir.iterdir()
        if entry.is_dir() and (entry / space).is_dir()
    )
    if not subjects:
        raise FileNotFoundError(
            f"No subject directories containing space '{space}' were found in "
            f"{base_dir}."
        )
    return subjects


def natural_sort_key(value: str) -> list[object]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", value)
    ]


def contrast_from_filename(filename: str) -> str | None:
    """Extract the original contrast name from a generated GIF filename."""
    stem = filename
    if stem.lower().endswith(".gif"):
        stem = stem[:-4]

    match = re.split(r"_vs_t2w_", stem, maxsplit=1, flags=re.IGNORECASE)
    if len(match) != 2:
        return None

    contrast = match[0]
    contrast = re.sub(
        r"(?:_masked)?_scaled$",
        "",
        contrast,
        flags=re.IGNORECASE,
    )
    return contrast or None


def discover_contrasts(
    base_dir: Path,
    subjects: Iterable[str],
    space: str,
    orientation: str,
    split: str,
    slice_value: str,
    threshold: str | None,
) -> list[str]:
    contrasts: set[str] = set()

    for subject in subjects:
        subject_root = base_dir / subject / space
        if not subject_root.is_dir():
            continue

        for path in subject_root.rglob("*.gif"):
            name = path.name.lower()

            if split.lower() not in name:
                continue
            if not re.search(
                rf"(?:^|_)atl_{re.escape(orientation)}(?:_|\.|$)",
                name,
            ):
                continue
            if not slice_matches(name, slice_value):
                continue
            if threshold is not None and threshold_type(path) != threshold:
                continue

            contrast = contrast_from_filename(path.name)
            if contrast is not None:
                contrasts.add(contrast)

    if not contrasts:
        raise FileNotFoundError(
            "No contrasts matched the selected orientation, split, slice, "
            "and threshold."
        )

    return sorted(contrasts, key=natural_sort_key)


def gif_candidates(
    subject_root: Path,
    contrast: str,
    orientation: str,
    split: str,
    slice_value: str,
    threshold: str | None,
) -> list[Path]:
    matches: list[Path] = []
    contrast_lower = contrast.lower()

    for path in subject_root.rglob("*.gif"):
        name = path.name.lower()

        if contrast_lower not in name:
            continue
        if split.lower() not in name:
            continue
        if not re.search(rf"(?:^|_)atl_{re.escape(orientation)}(?:_|\.|$)", name):
            continue
        if not slice_matches(name, slice_value):
            continue
        if threshold is not None and threshold_type(path) != threshold:
            continue

        matches.append(path.resolve())

    return sorted(matches)


def choose_gif(
    candidates: list[Path],
    subject: str,
    contrast: str,
    threshold: str | None,
) -> tuple[Path | None, str | None]:
    if not candidates:
        warnings.warn(
            f"No matching GIF for subject='{subject}', contrast='{contrast}'.",
            stacklevel=2,
        )
        return None, None

    types = {threshold_type(path) for path in candidates}
    types.discard(None)

    if threshold is None and len(types) > 1:
        warnings.warn(
            f"Both PRC and MAN GIFs match subject='{subject}', "
            f"contrast='{contrast}'. Specify --threshold.",
            stacklevel=2,
        )
        return None, None

    if len(candidates) > 1:
        warnings.warn(
            f"Multiple GIFs match subject='{subject}', contrast='{contrast}'. "
            f"Using: {candidates[0]}",
            stacklevel=2,
        )

    selected = candidates[0]
    return selected, threshold_type(selected)


def find_crop_box(
    image: Image.Image,
    threshold: int,
    margin: int,
    min_content: float,
    crop_basis: str,
) -> tuple[int, int, int, int]:
    def largest_contiguous_run(indices: np.ndarray) -> tuple[int, int]:
        """Return inclusive bounds of the longest consecutive index run."""
        split_points = np.flatnonzero(np.diff(indices) > 1) + 1
        runs = np.split(indices, split_points)
        longest = max(runs, key=lambda run: (len(run), run[-1] - run[0]))
        return int(longest[0]), int(longest[-1])

    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)

    if crop_basis == "t2w":
        gray = np.asarray(image.convert("L"))
        midpoint = image.width // 2
        right_foreground = gray[:, midpoint:] > threshold

        minimum_row_pixels = max(
            1,
            int(np.ceil((image.width - midpoint) * min_content)),
        )
        minimum_column_pixels = max(
            1,
            int(np.ceil(image.height * min_content)),
        )
        valid_rows = np.flatnonzero(
            np.count_nonzero(right_foreground, axis=1) >= minimum_row_pixels
        )
        valid_right_columns = np.flatnonzero(
            np.count_nonzero(right_foreground, axis=0)
            >= minimum_column_pixels
        )

        if valid_rows.size and valid_right_columns.size:
            upper, lower_inclusive = largest_contiguous_run(valid_rows)
            _, right_local_inclusive = largest_contiguous_run(
                valid_right_columns
            )
            right = midpoint + right_local_inclusive + 1
            half_width = right - midpoint
            left = midpoint - half_width
            lower = lower_inclusive + 1

            left = max(0, left - margin)
            upper = max(0, upper - margin)
            right = min(image.width, right + margin)
            lower = min(image.height, lower + margin)
            return (left, upper, right, lower)

        # Fall back if the T2w half is unexpectedly empty.
        crop_basis = "content"

    if crop_basis == "atlas":
        red = rgb[:, :, 0]
        green = rgb[:, :, 1]
        blue = rgb[:, :, 2]
        foreground = (
            (red >= 40)
            & ((red - green) >= 20)
            & ((red - blue) >= 20)
        )

        # Fall back safely for GIFs without a detectable red atlas overlay.
        if np.count_nonzero(foreground) < 20:
            gray = np.asarray(image.convert("L"))
            foreground = gray > threshold
            crop_basis = "content"
    else:
        gray = np.asarray(image.convert("L"))
        foreground = gray > threshold

    if crop_basis == "atlas":
        # The atlas contour is intentionally thin, so a single red contour
        # pixel is meaningful. Detached white slicer markers are not red and
        # therefore cannot affect this crop.
        minimum_row_pixels = 1
        minimum_column_pixels = 1
    else:
        minimum_row_pixels = max(
            1,
            int(np.ceil(image.width * min_content)),
        )
        minimum_column_pixels = max(
            1,
            int(np.ceil(image.height * min_content)),
        )

    valid_rows = np.flatnonzero(
        np.count_nonzero(foreground, axis=1) >= minimum_row_pixels
    )
    valid_columns = np.flatnonzero(
        np.count_nonzero(foreground, axis=0) >= minimum_column_pixels
    )

    if valid_rows.size == 0 or valid_columns.size == 0:
        return (0, 0, image.width, image.height)

    upper, lower_inclusive = largest_contiguous_run(valid_rows)
    left, right_inclusive = largest_contiguous_run(valid_columns)
    lower = lower_inclusive + 1
    right = right_inclusive + 1

    left = max(0, left - margin)
    upper = max(0, upper - margin)
    right = min(image.width, right + margin)
    lower = min(image.height, lower + margin)
    return (left, upper, right, lower)


def normalized_crop_box(
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> tuple[float, float, float, float]:
    width, height = image_size
    left, upper, right, lower = box
    return (
        left / width,
        upper / height,
        right / width,
        lower / height,
    )


def apply_normalized_crop(
    image: Image.Image,
    box: tuple[float, float, float, float],
) -> Image.Image:
    left = max(0, min(image.width - 1, round(box[0] * image.width)))
    upper = max(0, min(image.height - 1, round(box[1] * image.height)))
    right = max(left + 1, min(image.width, round(box[2] * image.width)))
    lower = max(upper + 1, min(image.height, round(box[3] * image.height)))
    return image.crop((left, upper, right, lower))


def pad_to_size(
    image: Image.Image,
    width: int,
    height: int,
    background: str,
) -> Image.Image:
    """Centre an image on a fixed canvas without changing its pixel scale."""
    canvas = Image.new("RGB", (width, height), background)
    x = (width - image.width) // 2
    y = (height - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def load_gif_frame(
    path: Path,
) -> Image.Image:
    with Image.open(path) as gif:
        gif.seek(0)
        image = gif.convert("RGB")

    return image


def fit_cell(
    image: Image.Image,
    width: int,
    height: int,
    background: str,
    image_scale: float,
) -> Image.Image:
    fitted = ImageOps.contain(
        image,
        (width, height),
        method=Image.Resampling.LANCZOS,
    )

    if image_scale != 1.0:
        scaled_width = max(1, round(fitted.width * image_scale))
        scaled_height = max(1, round(fitted.height * image_scale))
        fitted = fitted.resize(
            (scaled_width, scaled_height),
            Image.Resampling.LANCZOS,
        )

    cell = Image.new("RGB", (width, height), background)
    x = (width - fitted.width) // 2
    y = (height - fitted.height) // 2
    cell.paste(fitted, (x, y))
    return cell


def text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def safe_filename_component(value: str) -> str:
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    return value.strip("._-") or "unnamed"


def output_path(
    output_dir: Path,
    subjects: list[str],
    space: str,
    orientation: str,
    split: str,
    slice_value: str,
    threshold_label: str,
) -> Path:
    subject_label = (
        safe_filename_component(subjects[0])
        if len(subjects) == 1
        else "all_subjects"
    )
    metadata = "_".join(
        (
            safe_filename_component(space),
            orientation,
            split,
            f"slice-{safe_filename_component(slice_value)}",
            safe_filename_component(threshold_label),
        )
    )
    filename = f"{subject_label}_contrasts_{metadata}.png"
    return output_dir.expanduser().resolve() / filename


def print_configuration(
    args: argparse.Namespace,
    base_dir: Path,
    subjects: Iterable[str],
    orientation: str,
    split: str,
    slice_value: str,
) -> None:
    print("\n" + "=" * 72)
    print(" Subject-by-contrast figure")
    print("=" * 72)
    print(f"Base directory: {base_dir}")
    print(f"Space:          {args.space}")
    print(f"Subjects:       {', '.join(subjects)}")
    print(f"Contrasts:      {', '.join(args.contrasts)}")
    print(f"Orientation:    {orientation}")
    print(f"Split:          {split}")
    print(f"Slice:          {slice_value}")
    print(f"Threshold:      {args.threshold or 'auto-detect'}")
    print(f"Image scale:    {args.image_scale:g}")
    print(f"Scale mode:     {args.scale_mode}")
    print(f"Crop basis:     {args.crop_basis if args.autocrop else 'disabled'}")
    print(f"Output directory: {args.output_dir.expanduser().resolve()}")


def main() -> int:
    args = parse_args()
    base_dir = args.base_dir.expanduser().resolve()

    if not base_dir.is_dir():
        print(f"ERROR: Base directory does not exist: {base_dir}", file=sys.stderr)
        return 1

    orientation = ORIENTATION_ALIASES[args.orientation]
    split = SPLIT_ALIASES[args.split]
    slice_value = normalize_slice(args.slice)

    try:
        subjects = args.subjects or discover_subjects(base_dir, args.space)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.contrasts is None:
        try:
            args.contrasts = discover_contrasts(
                base_dir=base_dir,
                subjects=subjects,
                space=args.space,
                orientation=orientation,
                split=split,
                slice_value=slice_value,
                threshold=args.threshold,
            )
        except FileNotFoundError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(
            "Automatically detected contrasts: "
            + ", ".join(args.contrasts)
        )

    print_configuration(
        args,
        base_dir,
        subjects,
        orientation,
        split,
        slice_value,
    )

    selected: dict[tuple[str, str], Path | None] = {}
    detected_thresholds: set[str] = set()

    print("\nSearching for GIFs:")
    for subject in subjects:
        subject_root = base_dir / subject / args.space
        if not subject_root.is_dir():
            warnings.warn(
                f"Subject space directory does not exist: {subject_root}",
                stacklevel=2,
            )

        for contrast in args.contrasts:
            candidates = gif_candidates(
                subject_root=subject_root,
                contrast=contrast,
                orientation=orientation,
                split=split,
                slice_value=slice_value,
                threshold=args.threshold,
            )
            path, detected = choose_gif(
                candidates,
                subject,
                contrast,
                args.threshold,
            )
            selected[(subject, contrast)] = path
            if detected is not None:
                detected_thresholds.add(detected)

            if path is None:
                print(f"  MISSING: {subject} | {contrast}")
            else:
                print(f"  FOUND:   {path}")

    if not any(path is not None for path in selected.values()):
        print(
            "\nERROR: No matching GIFs were found; no figure was created.",
            file=sys.stderr,
        )
        return 1

    threshold_label = args.threshold or (
        next(iter(detected_thresholds))
        if len(detected_thresholds) == 1
        else "mixed-threshold"
    )

    # First pass: load all available images and calculate one normalized crop
    # per subject. The largest resulting crop defines a common source canvas
    # for the entire figure, so every row uses one pixel-to-display scale.
    loaded_images: dict[tuple[str, str], Image.Image] = {}
    subject_crops: dict[str, tuple[float, float, float, float] | None] = {}
    cropped_sizes: list[tuple[int, int]] = []

    print("\nPreparing shared crops and global scale:")
    for subject in subjects:
        available_contrasts: list[str] = []
        for contrast in args.contrasts:
            path = selected[(subject, contrast)]
            if path is not None:
                loaded_images[(subject, contrast)] = load_gif_frame(path)
                available_contrasts.append(contrast)

        shared_crop: tuple[float, float, float, float] | None = None
        if args.autocrop and available_contrasts:
            reference_contrast = available_contrasts[0]
            reference_image = loaded_images[(subject, reference_contrast)]
            reference_box = find_crop_box(
                reference_image,
                args.crop_threshold,
                args.crop_margin,
                args.crop_min_content,
                args.crop_basis,
            )
            shared_crop = normalized_crop_box(
                reference_box,
                reference_image.size,
            )
            print(
                f"  {subject}: crop from {reference_contrast} "
                f"{reference_box}"
            )

        subject_crops[subject] = shared_crop

        for contrast in available_contrasts:
            image = loaded_images[(subject, contrast)]
            if shared_crop is not None:
                image = apply_normalized_crop(image, shared_crop)
            cropped_sizes.append(image.size)

    global_source_width = max(width for width, _ in cropped_sizes)
    global_source_height = max(height for _, height in cropped_sizes)
    if args.scale_mode == "global":
        print(
            f"  Global source canvas: "
            f"{global_source_width} x {global_source_height} pixels"
        )
    else:
        print("  Display normalization: each subject fills the same cell region")

    try:
        font, font_source = load_font(args.font_size, args.font_file)
    except (FileNotFoundError, OSError) as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1

    print(f"\nFont: {font_source} ({args.font_size} px)")
    probe = Image.new("RGB", (10, 10))
    probe_draw = ImageDraw.Draw(probe)

    subject_label_width = max(
        text_size(probe_draw, subject, font)[0] for subject in subjects
    )
    subject_label_width += 2 * args.padding

    column_label_height = max(
        text_size(probe_draw, contrast, font)[1] for contrast in args.contrasts
    )
    column_label_height += 2 * args.padding

    canvas_width = (
        subject_label_width
        + len(args.contrasts) * args.cell_width
        + (len(args.contrasts) + 1) * args.padding
    )
    canvas_height = (
        column_label_height
        + len(subjects) * args.cell_height
        + (len(subjects) + 1) * args.padding
    )

    foreground = "white" if args.background == "black" else "black"
    canvas = Image.new("RGB", (canvas_width, canvas_height), args.background)
    draw = ImageDraw.Draw(canvas)

    grid_left = subject_label_width + args.padding
    grid_top = column_label_height + args.padding

    for column, contrast in enumerate(args.contrasts):
        x = grid_left + column * (args.cell_width + args.padding)
        width, height = text_size(draw, contrast, font)
        draw.text(
            (x + (args.cell_width - width) // 2, (column_label_height - height) // 2),
            contrast,
            fill=foreground,
            font=font,
        )

    for row, subject in enumerate(subjects):
        y = grid_top + row * (args.cell_height + args.padding)
        width, height = text_size(draw, subject, font)
        draw.text(
            (
                subject_label_width - width - args.padding,
                y + (args.cell_height - height) // 2,
            ),
            subject,
            fill=foreground,
            font=font,
        )

        for column, contrast in enumerate(args.contrasts):
            x = grid_left + column * (args.cell_width + args.padding)
            path = selected[(subject, contrast)]

            if path is None:
                draw.rectangle(
                    (x, y, x + args.cell_width - 1, y + args.cell_height - 1),
                    outline="red",
                    width=3,
                )
                message = "MISSING"
                width, height = text_size(draw, message, font)
                draw.text(
                    (
                        x + (args.cell_width - width) // 2,
                        y + (args.cell_height - height) // 2,
                    ),
                    message,
                    fill="red",
                    font=font,
                )
                continue

            image = loaded_images[(subject, contrast)]
            shared_crop = subject_crops[subject]
            if shared_crop is not None:
                image = apply_normalized_crop(image, shared_crop)
            if args.scale_mode == "global":
                image = pad_to_size(
                    image,
                    global_source_width,
                    global_source_height,
                    args.background,
                )
            cell = fit_cell(
                image,
                args.cell_width,
                args.cell_height,
                args.background,
                args.image_scale,
            )
            canvas.paste(cell, (x, y))

    output = output_path(
        args.output_dir,
        subjects,
        args.space,
        orientation,
        split,
        slice_value,
        threshold_label,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)

    print("\n" + "=" * 72)
    print(" Complete")
    print("=" * 72)
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

