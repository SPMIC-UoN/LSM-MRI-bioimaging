from pathlib import Path
import logging
import re

import h5py
import nibabel as nib
import numpy as np
import tifffile


LOGGER = logging.getLogger(__name__)

H5_CHUNK_SIZE = (64, 256, 256)


def _log_progress(prefix: str, current: int, total: int, step: int = 10):
    if total <= 0 or step <= 0:
        return

    if current >= total:
        LOGGER.info("%s: 100%% (%d/%d)", prefix, current, total)
        return

    prev_percent = int(((current - 1) * 100) / total) if current > 0 else 0
    curr_percent = int((current * 100) / total)

    if curr_percent // step > prev_percent // step:
        LOGGER.info(
            "%s: %d%% (%d/%d)",
            prefix,
            (curr_percent // step) * step,
            current,
            total,
        )


class _LazyTiffVolume:
    def __init__(self, tif_file, z_pages, shape, dtype):
        self._tif = tif_file
        self._z_pages = z_pages
        self.shape = shape
        self.dtype = dtype
        self.ndim = 3

    def __del__(self):
        try:
            self._tif.close()
        except Exception:
            pass

    def __getitem__(self, idx):
        if isinstance(idx, (int, np.integer)):
            return self._z_pages[int(idx)].asarray()

        if isinstance(idx, slice):
            start, stop, step = idx.indices(self.shape[0])
            slabs = [self._z_pages[i].asarray() for i in range(start, stop, step)]
            if not slabs:
                return np.empty((0,) + self.shape[1:], self.dtype)
            return np.stack(slabs)

        raise TypeError(f"Unsupported index type: {type(idx)}")


def _open_lazy_tiff(tif_path, raw_channel_idx):
    tif = tifffile.TiffFile(str(tif_path))
    series = tif.series[0]
    axes = series.axes.upper()
    shape = series.shape
    pages = list(series.pages)

    if axes == "ZYX":
        Z, Y, X = shape
        z_pages = pages

    elif axes == "CZYX":
        C, Z, Y, X = shape
        if raw_channel_idx >= C:
            raise ValueError(f"Channel {raw_channel_idx} out of range for C={C}")
        z_pages = pages[raw_channel_idx * Z:(raw_channel_idx + 1) * Z]

    elif axes == "TCZYX":
        T, C, Z, Y, X = shape
        if raw_channel_idx >= C:
            raise ValueError(f"Channel {raw_channel_idx} out of range for C={C}")
        offset = raw_channel_idx * Z
        z_pages = pages[offset:offset + Z]

    else:
        tif.close()
        raise NotImplementedError(f"Unhandled TIFF axes layout: {axes}")

    return _LazyTiffVolume(tif, z_pages, (Z, Y, X), series.dtype)


def read_volume(tif_path, raw_channel_idx):
    tif_path = Path(tif_path)
    LOGGER.info("Reading: %s", tif_path)

    try:
        data = tifffile.memmap(str(tif_path))
        LOGGER.info("memmap shape=%s dtype=%s", data.shape, data.dtype)

        if data.ndim == 3:
            return data
        if data.ndim == 4:
            return data[raw_channel_idx]
        if data.ndim == 5:
            return data[0, raw_channel_idx]

        raise ValueError(f"Unexpected data.ndim={data.ndim}")

    except (ValueError, NotImplementedError):
        pass

    try:
        vol = _open_lazy_tiff(tif_path, raw_channel_idx)
        LOGGER.info("lazy-pages shape=%s dtype=%s", vol.shape, vol.dtype)
        return vol

    except Exception as e:
        LOGGER.warning("Lazy TIFF reader failed: %s; falling back to full imread", e)

    data = tifffile.imread(str(tif_path))
    LOGGER.info("loaded shape=%s dtype=%s", data.shape, data.dtype)

    if data.ndim == 3:
        return data
    if data.ndim == 4:
        return data[raw_channel_idx]
    if data.ndim == 5:
        return data[0, raw_channel_idx]

    raise ValueError(f"Unexpected data.ndim={data.ndim}")


def downsample_3d(arr, ds):
    Z, Y, X = arr.shape
    fz, fy, fx = ds

    Zp = ((Z + fz - 1) // fz) * fz
    Yp = ((Y + fy - 1) // fy) * fy
    Xp = ((X + fx - 1) // fx) * fx

    out = np.empty((Zp // fz, Yp // fy, Xp // fx), dtype=np.float32)
    total_slabs = Zp // fz

    for z_out in range(total_slabs):
        z0 = z_out * fz
        z1 = min(z0 + fz, Z)

        slab = arr[z0:z1].astype(np.float32)

        pad_z = fz - slab.shape[0]
        if pad_z > 0 or Y < Yp or X < Xp:
            slab = np.pad(
                slab,
                ((0, pad_z), (0, Yp - Y), (0, Xp - X)),
                mode="edge",
            )

        out[z_out] = (
            slab.reshape(fz, Yp // fy, fy, Xp // fx, fx)
            .mean(axis=(0, 2, 4))
        )

        _log_progress("Downsampling slabs", z_out + 1, total_slabs)

    return out


def save_h5(data, path, chunk=H5_CHUNK_SIZE):
    path.parent.mkdir(parents=True, exist_ok=True)

    chunk = tuple(min(c, s) for c, s in zip(chunk, data.shape))
    slab_z = chunk[0]
    total_slabs = (data.shape[0] + slab_z - 1) // slab_z

    with h5py.File(path, "w") as h:
        ds = h.create_dataset(
            "volume",
            shape=data.shape,
            dtype=data.dtype,
            chunks=chunk,
            compression="lzf",
        )

        for slab_idx, z in enumerate(range(0, data.shape[0], slab_z), start=1):
            ds[z:z + slab_z] = data[z:z + slab_z]
            _log_progress("H5 write", slab_idx, total_slabs)

    LOGGER.info("H5 -> %s", path)


def save_previews(data, base_path, ds, voxel_um):
    base_path.parent.mkdir(parents=True, exist_ok=True)
    ds_str = f"ds{ds[0]}x{ds[1]}x{ds[2]}"

    LOGGER.info("Downsample %s by %s", data.shape, ds)
    small = downsample_3d(data, ds)
    LOGGER.info("Downsampled shape: %s", small.shape)

    tif_path = base_path.parent / f"{base_path.name}_{ds_str}.tif"
    tifffile.imwrite(tif_path, small)
    LOGGER.info("TIF -> %s", tif_path)

    reor = np.swapaxes(small, 0, 2)[::1, ::-1, ::-1] # Controls brain orientation

    aff = np.diag([
        voxel_um[2] * ds[2] * 1e-3,
        voxel_um[1] * ds[1] * 1e-3,
        voxel_um[0] * ds[0] * 1e-3,
        1.0,
    ])  # Controls orientation labels (eg in FSLeyes)

    nii_path = base_path.parent / f"{base_path.name}_{ds_str}.nii.gz"
    img = nib.Nifti1Image(reor, aff)
    img.header.set_xyzt_units(xyz="mm", t="sec")
    img.set_qform(aff, code=1)
    img.set_sform(aff, code=1)
    nib.save(img, nii_path)

    #LOGGER.info("NII -> %s", nii_path)
    orientation = nib.aff2axcodes(img.affine)

    LOGGER.info(
        "NII -> %s | shape=%s | voxel_mm=(%.6f, %.6f, %.6f) "
        "| orientation=%s",
        nii_path,
        reor.shape,
        voxel_um[2] * ds[2] * 1e-3,
        -voxel_um[1] * ds[1] * 1e-3,
        voxel_um[0] * ds[0] * 1e-3,
        orientation,
    )


def save_previews_old(data, base_path, ds, voxel_um):
    base_path.parent.mkdir(parents=True, exist_ok=True)
    ds_str = f"ds{ds[0]}x{ds[1]}x{ds[2]}"

    LOGGER.info("Downsample %s by %s", data.shape, ds)
    small = downsample_3d(data, ds)
    LOGGER.info("Downsampled shape: %s", small.shape)

    tif_path = base_path.parent / f"{base_path.name}_{ds_str}.tif"
    tifffile.imwrite(tif_path, small)
    LOGGER.info("TIF -> %s", tif_path)

    reor = np.swapaxes(small, 0, 2)[::-1, ::-1, ::-1]

    aff = np.diag([
        voxel_um[2] * ds[2] * 1e-3,
        voxel_um[1] * ds[1] * 1e-3,
        voxel_um[0] * ds[0] * 1e-3,
        1.0,
    ])

    nii_path = base_path.parent / f"{base_path.name}_{ds_str}.nii.gz"
    img = nib.Nifti1Image(reor, aff)
    img.header.set_xyzt_units(xyz="mm", t="sec")
    nib.save(img, nii_path)

    LOGGER.info("NII -> %s", nii_path)


def find_raw_datasets(main_dir, magnification, strains=None, channels=(0, 1)):
    main_dir = Path(main_dir)

    if strains is None:
        strains = sorted(p.name for p in main_dir.iterdir() if p.is_dir())

    datasets = []

    for strain in strains:
        mag_dir = main_dir / strain / magnification

        if not mag_dir.exists():
            LOGGER.warning("Skipping missing directory: %s", mag_dir)
            continue

        for ch in channels:
            pattern = f"*_C{ch:02d}*.ome.tif"

            for tiff_path in sorted(mag_dir.rglob(pattern)):
                rel_parent = tiff_path.parent.relative_to(mag_dir)
                raw_folder = "" if str(rel_parent) == "." else str(rel_parent)

                match = re.match(r"(.+)_C\d{2}.*\.ome\.tif$", tiff_path.name)
                if match:
                    session = match.group(1)
                else:
                    session = tiff_path.name.split(f"_C{ch:02d}")[0]

                datasets.append({
                    "strain": strain,
                    "magnification": magnification,
                    "raw_folder": raw_folder,
                    "session": session,
                    "channel": ch,
                    "path": tiff_path,
                })

    return datasets


def process_dataset(
    dataset,
    out_main,
    voxel,
    ds_factor,
    skip_existing=True,
    dry_run=False,
    keep_h5=False,
):
    strain = dataset["strain"]
    mag = dataset["magnification"]
    session = dataset["session"]
    ch = int(dataset["channel"])
    tif_path = Path(dataset["path"])

    out_dir = Path(out_main) / strain / mag
    out_h5 = out_dir / f"{session}_C{ch:02d}.h5"
    out_base = out_h5.with_suffix("")

    ds_str = f"ds{ds_factor[0]}x{ds_factor[1]}x{ds_factor[2]}"
    preview_tif = out_base.parent / f"{out_base.name}_{ds_str}.tif"
    preview_nii = out_base.parent / f"{out_base.name}_{ds_str}.nii.gz"

    LOGGER.info("%s", "=" * 64)
    LOGGER.info("%sStrain: %s", "[DRY-RUN] " if dry_run else "", strain)
    LOGGER.info("raw tif : %s", tif_path)
    LOGGER.info("out h5  : %s", out_h5)
    LOGGER.info("session : %s", session)
    LOGGER.info("channel : C%02d", ch)
    LOGGER.info("voxel   : %s", voxel)
    LOGGER.info("ds      : %s", ds_factor)
    LOGGER.info("keep_h5 : %s", keep_h5)
    LOGGER.info("%s", "=" * 64)

    if dry_run:
        status = "exists, skip" if skip_existing and preview_tif.exists() and preview_nii.exists() else "would convert"
        LOGGER.info("[%s]", status)
        return

    if skip_existing and preview_tif.exists() and preview_nii.exists():
        if keep_h5:
            if out_h5.exists():
                LOGGER.info("SKIP: previews and H5 already exist")
                return
        else:
            LOGGER.info("SKIP: previews already exist")
            return

    vol = read_volume(tif_path, ch)
    LOGGER.info("loaded vol: %s %s", vol.shape, vol.dtype)

    if keep_h5:
        save_h5(vol, out_h5)
    save_previews(vol, out_base, ds_factor, voxel)

    if not keep_h5:
        try:
            out_h5.unlink()
            LOGGER.info("Deleted intermediate H5: %s", out_h5)
        except FileNotFoundError:
            LOGGER.warning("H5 file already missing: %s", out_h5)
        except Exception as e:
            LOGGER.warning("Failed to delete H5 %s: %s", out_h5, e)
