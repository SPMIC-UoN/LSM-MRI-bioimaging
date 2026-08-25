"""Tests denoise.py::run_nordic without a real MATLAB/NORDIC install -
monkeypatches the module's `run()` call to fabricate NORDIC's output
files, then checks the MATLAB expression and fslcpgeom calls built.
"""

from __future__ import annotations

import pytest

import dmri_preproc.denoise as denoise_mod


def _make_fake_run(out_dir, out_name, matlab_ok=True, produce_denoised=True, produce_noisemap=True):
    calls = []

    def fake_run(cmd, step_name, log_dir=None):
        calls.append((step_name, cmd))
        if step_name == "nordic_denoise":
            if not matlab_ok:
                raise RuntimeError("nordic_denoise failed (exit 1): matlab error")
            out_dir.mkdir(parents=True, exist_ok=True)
            if produce_denoised:
                (out_dir / f"{out_name}.nii.gz").write_bytes(b"x")
            if produce_noisemap:
                (out_dir / f"{out_name}_noisemap.nii.gz").write_bytes(b"x")

    return calls, fake_run


def test_run_nordic_builds_expected_matlab_expression(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    calls, fake_run = _make_fake_run(out_dir, "desc-denoised_dwi")
    monkeypatch.setattr(denoise_mod, "run", fake_run)

    denoise_mod.run_nordic(
        magnitude=tmp_path / "mag.nii.gz",
        phase=tmp_path / "phase.nii.gz",
        out_dir=out_dir,
        out_name="desc-denoised_dwi",
        nordic_code_dir="/code/nordic",
    )

    step_names = [name for name, _ in calls]
    assert step_names == ["nordic_denoise", "fslcpgeom", "fslcpgeom"]

    matlab_cmd = calls[0][1]
    full_expr = matlab_cmd[-1]
    assert "addpath('/code/nordic')" in full_expr
    assert "ARG.temporal_phase = 3" in full_expr
    assert "ARG.write_gzipped_niftis = 1" in full_expr
    assert f"NIFTI_NORDIC('{tmp_path / 'mag.nii.gz'}'" in full_expr
    assert f"'{tmp_path / 'phase.nii.gz'}', 'desc-denoised_dwi', ARG)" in full_expr


def test_run_nordic_copies_geometry_onto_both_outputs(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    calls, fake_run = _make_fake_run(out_dir, "denoised")
    monkeypatch.setattr(denoise_mod, "run", fake_run)
    mag = tmp_path / "mag.nii.gz"

    denoised_path, noisemap_path = denoise_mod.run_nordic(
        magnitude=mag,
        phase=tmp_path / "phase.nii.gz",
        out_dir=out_dir,
        out_name="denoised",
        nordic_code_dir="/code/nordic",
    )

    assert denoised_path == out_dir / "denoised.nii.gz"
    assert (
        noisemap_path == out_dir / "denoised_noisemap.nii.gz"
    )  # lowercase "m" - see module docstring
    assert denoised_path.is_file()
    assert noisemap_path.is_file()

    fslcpgeom_calls = [cmd for name, cmd in calls if name == "fslcpgeom"]
    assert ["fslcpgeom", str(mag), str(denoised_path)] == fslcpgeom_calls[0]
    assert ["fslcpgeom", str(mag), str(noisemap_path)] == fslcpgeom_calls[1]


def test_run_nordic_skips_fslcpgeom_for_missing_noisemap(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    calls, fake_run = _make_fake_run(out_dir, "denoised", produce_noisemap=False)
    monkeypatch.setattr(denoise_mod, "run", fake_run)

    denoise_mod.run_nordic(
        magnitude=tmp_path / "mag.nii.gz",
        phase=tmp_path / "phase.nii.gz",
        out_dir=out_dir,
        out_name="denoised",
        nordic_code_dir="/code/nordic",
    )

    step_names = [name for name, _ in calls]
    assert step_names == ["nordic_denoise", "fslcpgeom"]


def test_run_nordic_raises_on_matlab_failure(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    _calls, fake_run = _make_fake_run(out_dir, "denoised", matlab_ok=False)
    monkeypatch.setattr(denoise_mod, "run", fake_run)

    with pytest.raises(RuntimeError, match="nordic_denoise failed"):
        denoise_mod.run_nordic(
            magnitude=tmp_path / "mag.nii.gz",
            phase=tmp_path / "phase.nii.gz",
            out_dir=out_dir,
            out_name="denoised",
            nordic_code_dir="/code/nordic",
        )


def test_run_nordic_raises_if_denoised_output_missing(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    _calls, fake_run = _make_fake_run(out_dir, "denoised", produce_denoised=False)
    monkeypatch.setattr(denoise_mod, "run", fake_run)

    with pytest.raises(RuntimeError, match="did not produce the expected output"):
        denoise_mod.run_nordic(
            magnitude=tmp_path / "mag.nii.gz",
            phase=tmp_path / "phase.nii.gz",
            out_dir=out_dir,
            out_name="denoised",
            nordic_code_dir="/code/nordic",
        )
