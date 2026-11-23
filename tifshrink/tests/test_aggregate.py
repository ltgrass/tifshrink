# -*- coding: utf-8 -*-
"""块式盒均值: 运算顺序、nodata 语义与恒等性"""
import numpy as np
import pytest

from tifshrink.aggregate import aggregate_box


def test_matches_explicit_block_mean_on_uint16():
    """与"先转 float64 再相加、最后除以有效个数"逐点等价

    这条锁住运算顺序本身: 若改成在源 dtype 里累加, uint16 大块会溢出;
    若先做整数除法, 结果会被截断。
    """
    rng = np.random.default_rng(0)
    values = rng.integers(0, 65535, (64, 96)).astype(np.uint16)
    valid = rng.random((64, 96)) > 0.3
    mean, ratio = aggregate_box(values, valid, 8)
    for i in range(0, 64, 8):
        for j in range(0, 96, 8):
            block = values[i:i + 8, j:j + 8].astype(np.float64)
            m = valid[i:i + 8, j:j + 8]
            assert mean[i // 8, j // 8] == pytest.approx(block[m].mean(), rel=1e-6)
            assert ratio[i // 8, j // 8] == pytest.approx(float(m.mean()))


def test_nodata_pixels_are_excluded_from_mean():
    values = np.array([[1.0, 1.0], [0.0, 0.0]], dtype=np.float32)
    valid = np.array([[True, True], [False, False]])
    mean, ratio = aggregate_box(values, valid, 2)
    assert mean[0, 0] == pytest.approx(1.0)
    assert ratio[0, 0] == pytest.approx(0.5)


def test_all_invalid_cell_is_nan_not_zero():
    mean, ratio = aggregate_box(np.zeros((2, 2), np.float32), np.zeros((2, 2), bool), 2)
    assert np.isnan(mean[0, 0]) and ratio[0, 0] == 0.0


def test_factor_one_is_identity():
    values = np.arange(6, dtype=np.float32).reshape(2, 3)
    valid = np.ones((2, 3), bool)
    mean, ratio = aggregate_box(values, valid, 1)
    np.testing.assert_array_equal(mean, values)


def test_block_smaller_than_factor_returns_empty():
    """块比合并因子还小时返回空数组, 调用方据此跳过, 而不是崩在 reshape 上"""
    mean, ratio = aggregate_box(np.zeros((3, 3), np.float32), np.ones((3, 3), bool), 4)
    assert mean.shape == (0, 0) and ratio.shape == (0, 0)
