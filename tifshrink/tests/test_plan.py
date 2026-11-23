# -*- coding: utf-8 -*-
"""降尺度规划: 选层、因子、输出网格与拒绝规则"""
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tifshrink import core
from tifshrink.core import RasterMeta, TifShrinkError

DOM_RES = 0.004423748950957508          # 实测: 一幅 6.7 万×9 万像元正射影像的 res[0]


def _meta(**kw):
    base = dict(path=Path("x.tif"), width=66790, height=90235, count=3, dtype="uint8",
                nodata=0.0, crs="EPSG:32652", transform=None, res_x=DOM_RES,
                res_y=DOM_RES, overviews=(2, 4, 8, 16, 32, 64, 128),
                descriptions=("", "", ""), colorinterp=("gray",) * 3)
    base.update(kw)
    return RasterMeta(**base)


def test_plan_matches_default_for_large_ortho_meta():
    p = core.plan_downscale(_meta(), 0.5)
    assert (p.source_level, p.factor, round(p.out_res, 4)) == (16, 7, 0.4955)
    assert (p.out_width, p.out_height) == (597, 806)
    assert p.sub_pixels == 49


def test_plan_rejects_target_finer_than_source():
    with pytest.raises(TifShrinkError) as e:
        core.plan_downscale(_meta(res_x=0.05, res_y=0.05, overviews=()), 0.02)
    assert e.value.code == "TARGET_TOO_FINE"


def test_plan_rejects_image_without_crs():
    with pytest.raises(TifShrinkError) as e:
        core.plan_downscale(_meta(crs=None), 0.5)
    assert e.value.code == "NO_CRS"


def test_plan_without_overviews_uses_full_resolution():
    p = core.plan_downscale(_meta(width=5000, height=5000, count=4, dtype="uint16",
                                 res_x=0.05, res_y=0.05, overviews=()), 0.5)
    assert (p.source_level, p.factor, p.out_res) == (1, 10, 0.5)
    assert p.sub_pixels == 100


def test_plan_target_equals_source_resolution_is_identity():
    p = core.plan_downscale(_meta(width=100, height=200, res_x=0.05, res_y=0.05,
                                 overviews=()), 0.05)
    assert (p.source_level, p.factor) == (1, 1)
    assert (p.out_width, p.out_height) == (100, 200)


def test_plan_degrades_source_level_when_source_pixels_exceed_cap():
    p = core.plan_downscale(_meta(), 0.5, sub_pixels_source_max=10_000_000)
    assert p.source_level == 32                     # 从 level 16 退到 level 32
    assert p.source_pixels <= 10_000_000
    assert p.notes and "退化" in "".join(p.notes)


def test_plan_never_goes_coarser_than_output_grid_level():
    p = core.plan_downscale(_meta(), 0.5, sub_pixels_source_max=1)
    assert p.source_level == 64                     # L0: 不允许比输出网格更粗
    assert any("上限" in n for n in p.notes)


def test_plan_handles_single_band_gray_source():
    p = core.plan_downscale(_meta(count=1, descriptions=(None,), colorinterp=("gray",)), 0.5)
    assert p.out_width == 597                       # 波段数不参与规划


def test_read_meta_reads_multiband_geotiff_without_overviews(tmp_path):
    """真实文件路径: 读得回波段数/dtype/分辨率/波段描述, 且无概览时报空"""
    p = tmp_path / "ms.tif"
    with rasterio.open(p, "w", driver="GTiff", width=500, height=500, count=4,
                       dtype="uint16", nodata=0, crs="EPSG:32652",
                       transform=from_origin(500000, 5000000, 0.05, 0.05)) as d:
        d.write(np.full((4, 500, 500), 1000, dtype="uint16"))
        d.descriptions = ("NIR", "RedEdge", "Red", "Green")
    m = core.read_meta(p)
    assert (m.count, m.dtype, m.overviews) == (4, "uint16", ())
    assert round(m.res_x, 3) == 0.05
    assert m.descriptions[0] == "NIR"


def test_read_meta_raises_open_failed(tmp_path):
    with pytest.raises(TifShrinkError) as e:
        core.read_meta(tmp_path / "nope.tif")
    assert e.value.code == "OPEN_FAILED"
