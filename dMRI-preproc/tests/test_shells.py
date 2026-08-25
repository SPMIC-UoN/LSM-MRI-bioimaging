import numpy as np
import pytest

from dmri_preproc.shells import detect_shell_blocks


def test_single_shell_with_interspersed_b0s():
    bvals = np.array([19.0] + [1013.0] * 8 + [19.0] + [1013.0] * 8)
    blocks = detect_shell_blocks(bvals)
    assert blocks == [(0, 18)]


def test_two_shells_back_to_back():
    shell_a = [19.0] + [1013.0] * 8 + [19.0] + [1013.0] * 8  # 18 volumes
    shell_b = [19.0] + [2500.0] * 8 + [19.0] + [2500.0] * 8  # 18 volumes
    bvals = np.array(shell_a + shell_b)
    blocks = detect_shell_blocks(bvals)
    assert blocks == [(0, 18), (18, 36)]


def test_leading_and_trailing_b0s_attach_to_neighbouring_shell():
    bvals = np.array([19.0, 19.0, 1000.0, 1000.0, 2500.0, 2500.0, 19.0, 19.0])
    blocks = detect_shell_blocks(bvals)
    # leading b0s -> first shell (1000), trailing b0s -> last shell (2500)
    assert blocks == [(0, 4), (4, 8)]


def test_near_identical_bvals_grouped_within_tolerance():
    bvals = np.array([19.0, 999.8, 1000.2, 999.9, 19.0])
    blocks = detect_shell_blocks(bvals, tol=50.0)
    assert blocks == [(0, 5)]


def test_no_non_b0_volumes_raises():
    with pytest.raises(ValueError, match="no non-b0 volumes"):
        detect_shell_blocks(np.array([19.0, 19.0, 19.0]))


def test_empty_bvals_raises():
    with pytest.raises(ValueError, match="empty"):
        detect_shell_blocks(np.array([]))
