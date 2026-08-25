from dmri_preproc.external import fsl, mrtrix
from dmri_preproc.external.matlab import add_path, matlab_command


def test_bet4animal_command():
    cmd = fsl.bet4animal("in.nii.gz", "out_prefix", f=0.075, z=6)
    assert cmd == ["bet4animal", "in.nii.gz", "out_prefix", "-m", "-z", "6", "-f", "0.075"]


def test_eddy_command_includes_required_flags():
    cmd = fsl.eddy(
        imain="d.nii.gz",
        mask="m.nii.gz",
        acqp="acqp.txt",
        index="idx.txt",
        bvecs="bvecs",
        bvals="bvals",
        topup_out="topup",
        out="out",
    )
    assert cmd[0] == "eddy"
    assert "--cnr_maps" in cmd
    assert "--data_is_shelled" in cmd
    assert "--imain=d.nii.gz" in cmd


def test_dtifit_command_kurt_flags():
    cmd = fsl.dtifit("d.nii.gz", "m.nii.gz", "bvals", "bvecs", "out", kurt=True, save_tensor=True)
    assert "--kurt" in cmd
    assert "--save_tensor" in cmd


def test_select_dwi_vols_command():
    cmd = fsl.select_dwi_vols("d.nii.gz", "bvals", "out.nii.gz", 0, [1000, 2500], obv="bvecs")
    assert cmd == [
        "select_dwi_vols",
        "d.nii.gz",
        "bvals",
        "out.nii.gz",
        "0",
        "-b",
        "1000",
        "-b",
        "2500",
        "-obv",
        "bvecs",
    ]


def test_fslcpgeom_command():
    cmd = fsl.fslcpgeom("in.nii.gz", "out.nii.gz")
    assert cmd == ["fslcpgeom", "in.nii.gz", "out.nii.gz"]


def test_mrdegibbs_command():
    cmd = mrtrix.mrdegibbs("in.nii.gz", "out.nii.gz")
    assert cmd == ["deGibbs3D", "in.nii.gz", "out.nii.gz", "-force"]


def test_dwidenoise_command_with_mask_and_noisemap():
    cmd = mrtrix.dwidenoise("in.nii.gz", "out.nii.gz", mask="m.nii.gz", noise_map="noise.nii.gz")
    assert cmd == [
        "dwidenoise",
        "in.nii.gz",
        "out.nii.gz",
        "-mask",
        "m.nii.gz",
        "-noise",
        "noise.nii.gz",
        "-force",
    ]


def test_matlab_command_wraps_statements_and_expression():
    cmd = matlab_command("foo(1)", statements_before=[add_path("/some/dir")])
    assert cmd[0] == "matlab"
    full_expr = cmd[-1]
    assert full_expr == (
        "addpath('/some/dir'); try; foo(1); catch ME; disp(getReport(ME)); exit(1); end; exit(0);"
    )
