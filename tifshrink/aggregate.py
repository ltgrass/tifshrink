# -*- coding: utf-8 -*-
"""tifshrink.aggregate - 块式盒均值 (k x k 非重叠平均, nodata 不参与)

与 rsbatch/raster.py 的 RasterSource.aggregate 是**同一套数学**: 运算顺序
(reshape -> sum(axis=(1,3), float64) -> 除以有效像元数) 刻意保持一致,
tifshrink/tests/test_aggregate.py 用逐点相等断言锁住, 防止两条链路日后各自漂移。
"""
from __future__ import annotations

import numpy as np


def aggregate_box(values: np.ndarray, valid: np.ndarray,
                  factor: int) -> tuple[np.ndarray, np.ndarray]:
    """k x k 合并: 返回 (均值 (h/k, w/k), 有效像元比例)

    完全无效的单元均值为 NaN (调用方据此写 nodata), 而不是 0 —— 否则
    nodata 区域会被当成"反射率为 0 的农田"参与反演。
    """
    h, w = values.shape
    hh, ww = h // factor, w // factor
    if hh == 0 or ww == 0:
        return (np.zeros((0, 0), dtype=np.float32),
                np.zeros((0, 0), dtype=np.float32))
    v = values[:hh * factor, :ww * factor]
    m = valid[:hh * factor, :ww * factor].astype(np.float32)
    vv = np.where(m > 0, v, 0.0).astype(np.float32)
    cells = vv.reshape(hh, factor, ww, factor)
    cnt = m.reshape(hh, factor, ww, factor)
    s = cells.sum(axis=(1, 3), dtype=np.float64)
    c = cnt.sum(axis=(1, 3), dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(c > 0, s / np.maximum(c, 1e-9), np.nan)
    ratio = c / float(factor * factor)
    return mean.astype(np.float32), ratio.astype(np.float32)
