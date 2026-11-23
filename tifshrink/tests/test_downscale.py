# -*- coding: utf-8 -*-
"""端到端降尺度: 输出网格、nodata 语义、取消、防覆盖、写盘失败

取消/进度用 block_pixels_max 注入小块 —— 默认块大小下 400x400 的影像只有一个块,
块边界永远触发不了, 那样测试等于没测。
"""
import os
import sys
import warnings

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tifshrink import core, downscale
from tifshrink.core import TifShrinkError


def _make_src(tmp_path, size=400, dtype="uint16", nodata=0, fill=1000, nodata_block=None):
    p = tmp_path / "big.tif"
    prof = dict(driver="GTiff", width=size, height=size, count=4, dtype=dtype, nodata=nodata,
                crs="EPSG:32652", transform=from_origin(500000, 5000000, 0.05, 0.05))
    data = np.full((4, size, size), fill, dtype=dtype)
    if nodata_block:
        data[:, :100, :100] = nodata
    with rasterio.open(p, "w", **prof) as d:
        d.write(data)
        d.descriptions = ("NIR(mock)", "RedEdge(mock)", "Red", "Green")
    return p


def test_downscale_writes_smaller_image_with_target_gsd(tmp_path):
    src = _make_src(tmp_path)
    dst = tmp_path / "out.tif"
    r = downscale.downscale(src, dst, 0.5)
    assert dst.exists() and r["out_res"] == 0.5
    with rasterio.open(dst) as d:
        assert (d.width, d.height) == (40, 40) and d.count == 4 and d.dtypes[0] == "uint16"
        assert d.transform.a == pytest.approx(0.5)


def test_nodata_pixels_stay_nodata_and_do_not_dilute_signal(tmp_path):
    src = _make_src(tmp_path, nodata_block=True)
    dst = tmp_path / "out.tif"
    downscale.downscale(src, dst, 0.5)
    with rasterio.open(dst) as d:
        a = d.read(1)
        assert a[15, 15] == 1000        # 完全有效单元保持原值 (覆盖源 150:160)
        assert a[0, 0] == 0             # 完全 nodata 单元仍为 nodata, 不是均值参与后的值
        assert a[2, 2] == 0             # 覆盖源 20:30, 仍在 nodata 块 (0:100) 内部


def test_refuses_to_overwrite_source(tmp_path):
    src = _make_src(tmp_path)
    with pytest.raises(TifShrinkError) as e:
        downscale.downscale(src, src, 0.5)
    assert e.value.code == "SAME_PATH"


def test_refuses_existing_output_without_overwrite(tmp_path):
    src = _make_src(tmp_path)
    dst = tmp_path / "out.tif"
    dst.write_text("x", encoding="utf-8")
    with pytest.raises(TifShrinkError) as e:
        downscale.downscale(src, dst, 0.5)
    assert e.value.code == "OUTPUT_EXISTS"
    assert downscale.downscale(src, dst, 0.5, overwrite=True)["out_res"] == 0.5


def test_cancel_leaves_no_final_file_but_keeps_partial(tmp_path):
    src = _make_src(tmp_path, size=1000)
    dst = tmp_path / "out.tif"
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(TifShrinkError) as e:
        downscale.downscale(src, dst, 0.5, cancel=cancel, block_pixels_max=250_000)
    assert e.value.code == "CANCELLED"
    assert not dst.exists() and (tmp_path / "out.tif.partial").exists()


def test_progress_is_monotonic_and_complete(tmp_path):
    src = _make_src(tmp_path, size=1000)
    seen = []
    downscale.downscale(src, tmp_path / "out.tif", 0.5,
                        progress=lambda d, t: seen.append((d, t)),
                        block_pixels_max=250_000)
    assert len(seen) == 4                       # 100x100 输出, 每块 50x50 -> 2x2 块
    assert seen[-1][0] == seen[-1][1] and [d for d, _ in seen] == sorted(d for d, _ in seen)


def test_estimate_is_upper_bound(tmp_path):
    # 专用夹具: 输出 200x200 (uint8x4 -> 上界 160 KB), 远大于分块填充与 TIFF 头开销,
    # 避免"极小影像的 512 分块填充"让实际文件反超未压缩上界
    src = _make_src(tmp_path, size=2000, dtype="uint8", fill=100)
    r = downscale.downscale(src, tmp_path / "out.tif", 0.5)
    assert r["bytes_out"] <= r["estimate_bytes"]


def test_float_dtype_values_are_not_quantized(tmp_path):
    """float32 反射率影像必须原值保留: 无条件 np.rint 会把 0.34 变成 0 (整幅归零)"""
    p = tmp_path / "f32.tif"
    with rasterio.open(p, "w", driver="GTiff", width=400, height=400, count=4,
                       dtype="float32", nodata=np.nan, crs="EPSG:32652",
                       transform=from_origin(500000, 5000000, 0.05, 0.05)) as d:
        d.write(np.full((4, 400, 400), 0.34, dtype="float32"))
        d.descriptions = ("NIR", "RedEdge", "Red", "Green")
    out = tmp_path / "o.tif"
    downscale.downscale(p, out, 0.5)
    with rasterio.open(out) as d:
        assert d.dtypes[0] == "float32"
        a = d.read(1)
    np.testing.assert_allclose(a[np.isfinite(a)], 0.34)


def test_mask_reading_emits_no_warnings(tmp_path):
    """4 波段 uint8 会被 GDAL 当作 RGBA, nodata 与 alpha 并存时 rasterio 每次读掩膜
    都发 NodataShadowWarning —— 掩膜语义本身必须与服务端一致(由 nodata 决定), 但
    大影像上千个块会把日志刷满, 因此就地静默这一个警告类别"""
    src = _make_src(tmp_path, size=2000, dtype="uint8", fill=100)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        downscale.downscale(src, tmp_path / "out.tif", 0.5)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows 的 chmod 不改变目录写权限, 该用例无从构造只读目录")
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root 不受目录权限限制")
def test_unwritable_output_dir_raises_write_failed(tmp_path):
    src = _make_src(tmp_path)
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        with pytest.raises(TifShrinkError) as e:
            downscale.downscale(src, ro / "out.tif", 0.5)
        assert e.value.code == "WRITE_FAILED"
    finally:
        ro.chmod(0o700)
