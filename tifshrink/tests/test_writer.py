# -*- coding: utf-8 -*-
"""落盘 profile 与波段元数据保真

波段描述与 colorinterp 一旦丢失, 下游就认不出 NIR/RedEdge/Red/Green ——
压缩后的影像在后续处理链路里会报"缺少必需波段"或退化成占位数据。
"""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tifshrink import core, writer


def _make_src(tmp_path, count=4, dtype="uint16",
              descriptions=("NIR(mock)", "RedEdge(mock)", "Red", "Green"),
              colorinterp=None):
    p = tmp_path / "src.tif"
    prof = dict(driver="GTiff", width=200, height=100, count=count, dtype=dtype,
                nodata=0, crs="EPSG:32652", transform=from_origin(500000, 5000000, 0.05, 0.05))
    with rasterio.open(p, "w", **prof) as d:
        d.write(np.full((count, 100, 200), 1000, dtype=dtype))
        d.descriptions = descriptions
        if colorinterp is not None:
            d.colorinterp = colorinterp
    return p


def _roundtrip(tmp_path, **kw):
    """源影像 -> 按输出 profile 写一遍 -> 读回, 返回 (源 meta, 输出数据集内容)"""
    src = _make_src(tmp_path, **kw)
    meta = core.read_meta(src)
    dst = tmp_path / "out.tif"
    with rasterio.open(dst, "w", **writer.write_profile(meta, core.plan_downscale(meta, 0.5))) as d:
        writer.apply_band_metadata(d, meta)
    with rasterio.open(dst) as d:
        return meta, d.descriptions, tuple(c.name for c in d.colorinterp)


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
    meta, descriptions, colorinterp = _roundtrip(tmp_path)
    assert descriptions == meta.descriptions
    assert colorinterp == meta.colorinterp


def test_empty_description_is_normalized_to_none(tmp_path):
    """GDAL 对"没有描述"的读回值是 None; 空串不归一会让读-写-读与原图不一致"""
    meta, descriptions, _ = _roundtrip(tmp_path, descriptions=("NIR", "", "Red", "Green"))
    assert descriptions == ("NIR", None, "Red", "Green")


def test_output_res_label():
    assert writer.output_res_label(0.4954599581938426) == "0.4955"
