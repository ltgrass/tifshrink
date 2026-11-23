# -*- coding: utf-8 -*-
"""tifshrink.writer - 输出影像的 profile 与波段元数据

两件事必须做对, 否则下游静默出错:
  * transform 用**未四舍五入**的 out_res 计算, 避免累计漂移;
  * descriptions 与 colorinterp 逐波段复制 —— rasterio 的 profile 不携带它们,
    而服务端 rsbatch.raster.detect_band_map() 正是靠这两项识别 nir/re/red/green。
"""
from __future__ import annotations

from rasterio.enums import ColorInterp
from rasterio.transform import Affine

from . import config as C


def write_profile(meta, plan) -> dict:
    """降尺度输出影像的 rasterio profile (可直接 **profile 传给 rasterio.open)"""
    step = plan.source_level * plan.factor
    res_x = meta.res_x * step
    res_y = meta.res_y * step
    transform = Affine(res_x, 0.0, meta.transform.c,
                       0.0, -res_y, meta.transform.f)
    return dict(
        driver="GTiff",
        width=int(plan.out_width), height=int(plan.out_height),
        count=int(meta.count), dtype=meta.dtype, nodata=meta.nodata,
        crs=meta.crs, transform=transform,
        tiled=True, blockxsize=C.TILE_SIZE, blockysize=C.TILE_SIZE,
        compress="deflate", zlevel=C.DEFLATE_LEVEL,
        BIGTIFF="IF_SAFER",
    )


def apply_band_metadata(dst, meta) -> None:
    """把波段描述与 colorinterp 写到已打开的目标数据集

    空字符串归一为 None: GDAL 对"没有描述"的读回值是 None, 不归一会导致
    读-写-读之后与原图比不一致。
    """
    if meta.descriptions:
        dst.descriptions = tuple(d or None for d in meta.descriptions)
    if meta.colorinterp:
        dst.colorinterp = tuple(ColorInterp[name] for name in meta.colorinterp)


def output_res_label(out_res: float) -> str:
    """输出分辨率 -> 文件名里用的标签 (去尾零: 0.4955 / 0.5 / 10)"""
    return f"{round(float(out_res), 4):g}"
