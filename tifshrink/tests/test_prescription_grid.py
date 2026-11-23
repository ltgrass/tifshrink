# -*- coding: utf-8 -*-
"""处方图对齐: 两组实验的作业单元网格可能因 factor 取整而不同, 比较前必须落到同一网格"""
import numpy as np
import rasterio
from rasterio.transform import from_origin

from tifshrink.compare import align_to_common_grid


def _write(path, arr, res):
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0],
                       count=1, dtype="float32", nodata=-9999,
                       crs="EPSG:32652", transform=from_origin(500000, 5000000, res, res)) as d:
        d.write(arr.astype("float32"), 1)


def test_align_to_common_grid_matches_shapes(tmp_path):
    a = np.full((25, 25), 100.0, np.float32)
    b = np.full((26, 26), 100.0, np.float32)
    pa, pb = tmp_path / "a.tif", tmp_path / "b.tif"
    _write(pa, a, 10.0)
    _write(pb, b, 9.91)
    ga, gb = align_to_common_grid(pa, pb, res=10.0)
    assert ga.shape == gb.shape
    np.testing.assert_allclose(ga, gb, atol=1e-3)


def test_align_keeps_nodata_out_of_the_average(tmp_path):
    """一侧有大片 nodata 时, 不能被当成 0 参与平均"""
    a = np.full((20, 20), 100.0, np.float32)
    b = np.full((20, 20), -9999.0, np.float32)
    b[:10, :] = 100.0
    pa, pb = tmp_path / "a.tif", tmp_path / "b.tif"
    _write(pa, a, 10.0)
    _write(pb, b, 10.0)
    ga, gb = align_to_common_grid(pa, pb, res=10.0)
    np.testing.assert_allclose(ga, 100.0, atol=1e-3)
    np.testing.assert_allclose(gb[:10, :], 100.0, atol=1e-3)
    assert np.isnan(gb[10:, :]).all()
