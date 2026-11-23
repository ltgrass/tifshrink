# -*- coding: utf-8 -*-
"""tifshrink.downscale - 端到端降尺度 (分块流式, 内存与影像大小无关)

约定:
  * 先写 <dst>.partial, 成功后 os.replace 成 <dst> —— 取消/失败时绝不留下一个
    看起来正常、实际不完整的输出文件; 也绝不删除任何文件 (含 .partial)。
  * nodata 像元不参与平均; 完全无效的输出像元写 nodata。
  * 输出保持源 dtype, 均值显式 rint 后再落盘 (量化 <= 0.5 DN)。
"""
from __future__ import annotations

import math
import os
import time
import warnings
from pathlib import Path

import numpy as np

from . import config as C
from . import core
from . import writer
from .aggregate import aggregate_box
from .core import TifShrinkError


def estimate_uncompressed_bytes(plan, count: int, dtype: str) -> int:
    """像元数据的未压缩上界 (deflate 前的口径; 实际文件通常再小 1.5~2.5 倍)

    注意: 只统计像元数据, 不含 TIFF 头与 512 分块填充 —— 对极小影像实际文件
    可能略大于该值, 对真实尺寸的影像它是稳妥的上界。
    """
    itemsize = C.DTYPE_ITEMSIZE.get(dtype, 2)
    return int(plan.out_width) * int(plan.out_height) * int(count) * itemsize


def downscale(src, dst, target_m: float, *, progress=None, cancel=None,
              overwrite: bool = False,
              block_pixels_max: int = C.READ_PIXELS_MAX) -> dict:
    """一幅影像 -> 一幅降分辨率影像; 返回结果 dict (JSON-safe)"""
    import rasterio
    from rasterio.errors import NodataShadowWarning
    from rasterio.windows import Window

    src, dst = Path(src), Path(dst)
    if _same_file(src, dst):
        raise TifShrinkError("SAME_PATH", f"输出路径与源文件相同, 拒绝覆盖原图: {src.name}")
    if dst.exists() and not overwrite:
        raise TifShrinkError("OUTPUT_EXISTS", f"输出文件已存在: {dst.name} (如需覆盖请显式开启)")

    meta = core.read_meta(src)
    plan = core.plan_downscale(meta, target_m)
    partial = dst.with_name(dst.name + ".partial")
    total = _block_count(plan, block_pixels_max)
    t0 = time.time()
    done = 0

    try:
        with rasterio.open(src, overview_level=_ovr_index(meta, plan.source_level)) as s:
            try:
                d = rasterio.open(partial, "w", **writer.write_profile(meta, plan))
            except Exception as e:                              # noqa: BLE001
                raise TifShrinkError(
                    "WRITE_FAILED",
                    f"无法创建输出文件 ({e.__class__.__name__}: {e}); "
                    f"请检查目录写权限与磁盘空间") from e
            with d:
                writer.apply_band_metadata(d, meta)
                nodata = meta.nodata if meta.nodata is not None else 0.0
                # 掩膜语义由 nodata 决定 (见 NodataShadowWarning 的含义),
                # 但该警告每次读掩膜都发一次, 大影像上千个块会把日志刷满 —— 只静默这一个类别。
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", NodataShadowWarning)
                    for win, out_win in _iter_windows(plan, block_pixels_max):
                        if cancel is not None and cancel():
                            raise TifShrinkError(
                                "CANCELLED", "已取消 (未完成的中间文件保留为 .partial)")
                        data = s.read(window=win, boundless=True, fill_value=0,
                                      out_dtype=np.float32)
                        valid = s.read_masks(1, window=win, boundless=True) > 0
                        out = np.empty((meta.count, out_win.height, out_win.width),
                                       dtype=np.float32)
                        for b in range(meta.count):
                            mean, ratio = aggregate_box(data[b], valid, plan.factor)
                            out[b] = np.where(ratio > 0, mean, nodata)
                        d.write(_cast_to_dtype(out, meta.dtype), window=out_win)
                        done += 1
                        if progress is not None:
                            progress(done, total)
    except TifShrinkError:
        raise
    except Exception as e:                                      # noqa: BLE001
        raise TifShrinkError("PROCESS_FAILED",
                             f"处理失败 ({e.__class__.__name__}: {e}); "
                             f"中间文件保留为 {partial.name}") from e

    os.replace(partial, dst)
    bytes_out = dst.stat().st_size
    return {
        "src": str(src), "dst": str(dst), "target_m": float(target_m),
        "out_res": round(plan.out_res, 4), "out_width": plan.out_width,
        "out_height": plan.out_height, "source_level": plan.source_level,
        "factor": plan.factor, "sub_pixels": plan.sub_pixels,
        "bytes_out": int(bytes_out),
        "estimate_bytes": estimate_uncompressed_bytes(plan, meta.count, meta.dtype),
        "elapsed_sec": round(time.time() - t0, 3),
        "notes": list(plan.notes),
    }


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------
def _same_file(src: Path, dst: Path) -> bool:
    try:
        return src.resolve() == dst.resolve()
    except OSError:                                             # noqa: BLE001
        return False


def _cast_to_dtype(values: np.ndarray, dtype: str) -> np.ndarray:
    """回写源 dtype: **只有整数类型才取整**

    无条件 np.rint 会把 float 源 (例如 Pix4D/Agisoft 的 float32 反射率 ortho)
    的小数全部抹平 —— 0.34 变成 0, 整幅影像归零, 而 dtype/nodata 元数据看起来
    完全正常, 用户与服务端都无从察觉。
    """
    if np.issubdtype(np.dtype(dtype), np.integer):
        values = np.rint(values)
    return values.astype(dtype)


def _ovr_index(meta, level: int) -> int | None:
    """概览倍率 -> rasterio 的 overview_level 序号 (1 = 原分辨率, 返回 None)"""
    if level == 1:
        return None
    return list(meta.overviews).index(level)


def _block_rows(plan, block_pixels_max: int) -> int:
    return max(1, int((float(block_pixels_max) ** 0.5) // max(1, plan.factor)))


def _block_count(plan, block_pixels_max: int) -> int:
    rows = _block_rows(plan, block_pixels_max)
    return (math.ceil(plan.out_height / rows) * math.ceil(plan.out_width / rows))


def _iter_windows(plan, block_pixels_max: int):
    """产出 (源窗口, 输出窗口); 源窗口按 factor 对齐, 保证是整数倍盒式均值"""
    from rasterio.windows import Window

    rows = _block_rows(plan, block_pixels_max)
    f = plan.factor
    for r0 in range(0, plan.out_height, rows):
        for c0 in range(0, plan.out_width, rows):
            nr = min(rows, plan.out_height - r0)
            nc = min(rows, plan.out_width - c0)
            yield (Window(col_off=c0 * f, row_off=r0 * f, width=nc * f, height=nr * f),
                   Window(col_off=c0, row_off=r0, width=nc, height=nr))
