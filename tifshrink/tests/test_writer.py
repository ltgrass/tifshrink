# -*- coding: utf-8 -*-
"""落盘 profile 与波段元数据保真

波段描述/colorinterp 一旦丢失, 服务端的 detect_band_map() 就认不出 NIR/RE,
压缩后的影像在服务端会直接报"缺少必需波段"或退化成 mock。
"""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tifshrink import core, writer


def _make_src(tmp_path, count=4, dtype="uint16",
              descriptions=("NIR(mock)", "RedEdge(mock)", "Red", "Green")):
    p = tmp_path / "src.tif"
    prof = dict(driver="GTiff", width=200, height=100, count=count, dtype=dtype,
                nodata=0, crs="EPSG:32652", transform=from_origin(500000, 5000000, 0.05, 0.05))
    with rasterio.open(p, "w", **prof) as d:
        d.write(np.full((count, 100, 200), 1000, dtype=dtype))
        d.descriptions = descriptions
    return p


def test_profile_keeps_dtype_nodata_crs_and_structure(tmp_path):
    src = _make_src(tmp_path)
    meta = core.read_meta(src)
    prof = writer.write_profile(meta, core.plan_downscale(meta, 0.5))
    assert prof["dtype"] == "uint16" and prof["nodata"] == 0
    assert prof["crs"] == meta.crs and prof["compress"] == "deflate"
    assert prof["tiled"] is True and prof["blockxsize"] == 512 and prof["blockysize"] == 512
    assert "overviews" not in prof


def test_transform_keeps_origin_and_scales_pixel_size(tmp_path):
    src = _make_src(tmp_path)
    meta = core.read_meta(src)
    plan = core.plan_downscale(meta, 0.5)
    prof = writer.write_profile(meta, plan)
    assert (prof["transform"].c, prof["transform"].f) == (meta.transform.c, meta.transform.f)
    assert prof["transform"].a == pytest.approx(
        meta.res_x * plan.source_level * plan.factor, rel=1e-12)
    assert (prof["width"], prof["height"]) == (plan.out_width, plan.out_height)


def test_descriptions_and_colorinterp_survive_roundtrip(tmp_path):
    src = _make_src(tmp_path)
    meta = core.read_meta(src)
    dst = tmp_path / "out.tif"
    with rasterio.open(dst, "w", **writer.write_profile(meta, core.plan_downscale(meta, 0.5))) as d:
        writer.apply_band_metadata(d, meta)
    with rasterio.open(dst) as d:
        assert d.descriptions == meta.descriptions
        assert tuple(c.name for c in d.colorinterp) == meta.colorinterp


def test_detect_band_map_identical_before_and_after(tmp_path):
    # 独立仓 (ltgrass/tifshrink) 没有 rsbatch, 这条 skip; 主仓照常运行
    detect_band_map = pytest.importorskip(
        "rsbatch.raster", reason="仅主仓可跑: 需要 rsbatch 的波段识别实现").detect_band_map
    src = _make_src(tmp_path)
    meta = core.read_meta(src)
    dst = tmp_path / "out.tif"
    with rasterio.open(dst, "w", **writer.write_profile(meta, core.plan_downscale(meta, 0.5))) as d:
        writer.apply_band_metadata(d, meta)
    with rasterio.open(src) as a, rasterio.open(dst) as b:
        assert detect_band_map(a) == detect_band_map(b) == {"re": 2, "nir": 1, "red": 3, "green": 4}


def test_output_res_label():
    assert writer.output_res_label(0.4954599581938426) == "0.4955"
