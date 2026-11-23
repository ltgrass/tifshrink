# -*- coding: utf-8 -*-
"""tifshrink.compare - 两幅栅格的对齐与偏差统计 (供对照实验与测试复用)

只依赖 rasterio/numpy (工具本体的依赖纪律)。
两幅栅格的像元边长可能因 factor 取整而不同 (例如 10.19 m 与 9.91 m),
比较前必须重采样到同一网格, 否则逐像元比较没有意义。
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject


def align_to_common_grid(a, b, res: float):
    """把两幅处方图重采样到同一网格 (以 a 的左上角与范围为基准, 像元 res 米)

    nodata 不参与平均 (average 重采样会跳过), 无覆盖区域为 NaN。
    返回 (grid_a, grid_b), 两者形状相同。
    """
    with rasterio.open(Path(a)) as sa, rasterio.open(Path(b)) as sb:
        transform = from_origin(sa.transform.c, sa.transform.f, res, res)
        width = int(math.ceil(sa.width * sa.transform.a / res))
        height = int(math.ceil(sa.height * abs(sa.transform.e) / res))
        grid = [_reproject_one(s, transform, width, height, sa.crs) for s in (sa, sb)]
    return grid[0], grid[1]


def deviation_stats(grid_a: np.ndarray, grid_b: np.ndarray) -> dict:
    """共同网格上的偏差统计 (只在两者都有效的单元上算)"""
    both = np.isfinite(grid_a) & np.isfinite(grid_b)
    if not both.any():
        return {"cells": 0}
    x, y = grid_a[both].astype(np.float64), grid_b[both].astype(np.float64)
    diff = np.abs(x - y)
    base = float(np.mean(x))
    rel = float(np.mean(diff) / base * 100.0) if base else float("nan")
    return {
        "cells": int(both.sum()),
        "mean_a": round(float(np.mean(x)), 3),
        "mean_b": round(float(np.mean(y)), 3),
        "mean_rel_pct": round(rel, 3),
        "max_abs_diff": round(float(diff.max()), 3),
        "p95_abs_diff": round(float(np.percentile(diff, 95)), 3),
        "p95_rel_pct": round(float(np.percentile(diff, 95) / base * 100.0), 3) if base else None,
    }


def _reproject_one(src, transform, width: int, height: int, crs) -> np.ndarray:
    dst = np.full((height, width), np.nan, dtype=np.float32)
    reproject(
        source=rasterio.band(src, 1), destination=dst,
        src_transform=src.transform, src_crs=src.crs,
        src_nodata=src.nodata, dst_transform=transform, dst_crs=crs,
        dst_nodata=np.nan, resampling=Resampling.average,
    )
    return dst
