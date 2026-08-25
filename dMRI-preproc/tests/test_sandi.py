from pathlib import Path

import dmri_preproc.sandi as sandi_mod


def test_fit_sandi_calls_vendored_function_with_expected_args(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "dmri_preproc.sandi.run",
        lambda cmd, step_name, log_dir=None: calls.append((step_name, cmd)),
    )

    sandi_mod.fit_sandi(
        sandi_dir=tmp_path,
        delta_ms=20.0,
        small_delta_ms=7.5,
        toolbox_dir="/path/to/toolbox",
        with_dot=True,
        dsoma_init=2.0,
    )

    assert calls[0][0] == "sandi_fit"
    full_expr = calls[0][1][-1]
    assert "dmri_preproc_sandi_batch_analysis(" in full_expr
    assert f"'{tmp_path}', 20.0, 7.5, [], 1, 2.0)" in full_expr
    assert f"addpath('{sandi_mod._MATLAB_DIR}')" in full_expr
    assert "addpath('/path/to/toolbox')" in full_expr


def test_vendored_sandi_script_is_bundled():
    assert (sandi_mod._MATLAB_DIR / "dmri_preproc_sandi_batch_analysis.m").is_file()


def test_prepare_sandi_data_lays_out_expected_files(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "dmri_preproc.sandi.run",
        lambda cmd, step_name, log_dir=None: calls.append((step_name, cmd)),
    )

    data = tmp_path / "dwi.nii.gz"
    bvals = tmp_path / "dwi.bval"
    bvecs = tmp_path / "dwi.bvec"
    mask = tmp_path / "mask.nii.gz"
    for f in (data, bvals, bvecs, mask):
        f.write_bytes(b"x")

    sandi_dir = tmp_path / "sandi"
    prep_dir = sandi_mod.prepare_sandi_data(data, bvals, bvecs, mask, sandi_dir)

    assert prep_dir == Path(sandi_dir) / "derivatives" / "preprocessed" / "sub-01" / "ses-01"
    basename = "sub-01_ses-01_acq-01_run-01_desc-preproc"
    assert (prep_dir / f"{basename}_dwi.nii.gz").is_file()
    assert (prep_dir / f"{basename}_mask.nii.gz").is_file()
    assert calls[0][0] == "dwidenoise_sandi_prep"
