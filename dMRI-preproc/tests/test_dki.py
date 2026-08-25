from dmri_preproc.dki import DKI_SHELLS, fit_dki, select_shells


def test_dki_shells_match_paper_methods():
    # b = [1, 2.5, 5.5, 8.5] ms/um^2 == [1000, 2500, 5500, 8500] s/mm^2
    assert DKI_SHELLS == [1000, 2500, 5500, 8500]


def test_select_shells_calls_expected_command(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "dmri_preproc.dki.run", lambda cmd, step_name, log_dir=None: calls.append((step_name, cmd))
    )

    out = tmp_path / "subset.nii.gz"
    data_path, bval_path, bvec_path = select_shells(
        "data.nii.gz", "bvals", "bvecs", out, DKI_SHELLS
    )

    assert data_path == out
    assert bval_path == tmp_path / "subset.nii.gz.bval"
    assert bvec_path == tmp_path / "subset.nii.gz.bvec"
    assert calls[0][0] == "select_dwi_vols"
    assert calls[0][1][0] == "select_dwi_vols"


def test_fit_dki_returns_kurt_path(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "dmri_preproc.dki.run", lambda cmd, step_name, log_dir=None: calls.append((step_name, cmd))
    )

    out_prefix = tmp_path / "dki"
    kurt_path = fit_dki("data.nii.gz", "mask.nii.gz", "bvals", "bvecs", out_prefix)

    assert kurt_path == tmp_path / "dki_kurt.nii.gz"
    assert calls[0][0] == "dtifit_dki"
    assert "--kurt" in calls[0][1]
    assert "--save_tensor" in calls[0][1]
