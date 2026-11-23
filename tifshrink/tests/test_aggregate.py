# -*- coding: utf-8 -*-
"""块式盒均值: 必须与 rsbatch.raster.RasterSource.aggregate 逐点一致

两条链路(服务端自跑 / 工具压缩后服务端再跑)的数值口径就靠这条断言锁住。

独立性说明: 独立仓 (ltgrass/tifshrink) 里没有 rsbatch, 只有这一条一致性断言会
skip; 护栏本身在主仓 (rice-fert-engine) 全量运行。
"""
import numpy as np
import pytest

from tifshrink.aggregate import aggregate_box


def test_matches_rsbatch_aggregate_pointwise():
    RasterSource = pytest.importorskip(
        "rsbatch.raster", reason="仅主仓可跑: 需要 rsbatch 的参考实现").RasterSource
    rng = np.random.default_rng(0)
    values = rng.random((64, 96), dtype=np.float32)
    valid = rng.random((64, 96)) > 0.3
    mine = aggregate_box(values, valid, 8)
    theirs = RasterSource.aggregate(values, valid, 8)
    for a, b in zip(mine, theirs):
        np.testing.assert_allclose(a, b, rtol=0, atol=0, equal_nan=True)


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
