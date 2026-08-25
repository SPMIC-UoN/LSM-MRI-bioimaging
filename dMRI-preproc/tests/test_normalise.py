import numpy as np

from dmri_preproc.normalise import b0_mean_volume, normalise_merged, normalise_shell


def test_b0_mean_volume_averages_only_b0_volumes():
    data = np.zeros((2, 2, 2, 3))
    data[..., 0] = 10.0  # b0
    data[..., 1] = 999.0  # dwi
    data[..., 2] = 20.0  # b0
    bvals = np.array([0.0, 1000.0, 0.0])

    mean = b0_mean_volume(data, bvals)
    assert np.allclose(mean, 15.0)


def test_normalise_shell_scales_whole_block_by_b0_ratio():
    data = np.full((2, 2, 2, 2), 50.0)
    bvals = np.array([0.0, 1000.0])
    reference_b0_mean = np.full((2, 2, 2), 25.0)  # own b0 (50) is 2x reference

    out = normalise_shell(data, bvals, reference_b0_mean)
    assert np.allclose(out, 25.0)


def test_normalise_merged_matches_all_blocks_to_reference_block():
    # two shells, 4 volumes each: [b0, dwi, dwi, dwi] (each shell leads
    # with its own b0, matching the real acquisition convention)
    bvals = np.array([0.0, 1000.0, 1000.0, 1000.0, 0.0, 2500.0, 2500.0, 2500.0])
    data = np.ones((2, 2, 2, 8))
    data[..., 0:4] = 10.0  # first shell: b0 level 10
    data[..., 4:8] = 20.0  # second shell: b0 level 20 (2x first shell)

    out = normalise_merged(data, bvals, reference_block_index=0)

    assert np.allclose(out[..., 0:4], 10.0)  # reference block unchanged
    assert np.allclose(out[..., 4:8], 10.0)  # second block scaled down to match
