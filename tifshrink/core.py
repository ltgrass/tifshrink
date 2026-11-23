# -*- coding: utf-8 -*-
"""tifshrink.core - 元数据读取与降尺度规划 (纯函数, 不写盘)

规划规则 (设计文档 §4.2):
  1) 定输出网格: L0 = 分辨率仍细于 target 的最粗一级概览 (与 rsbatch 同一判据)
  2) 定源数据层: 比 L0 再细 SRC_LEVEL_STEPS 级 —— 每个输出像元由 factor^2 个
     细像元均值得到, 而不是采 1 个抽稀点 (DOM.tif 的概览是抽稀金字塔, 见 §4.1)
  3) 源层像元超限时向更粗回退, 但**绝不超过 L0**: 比 L0 更粗等于输出粗于用户要求
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from . import config as C


class TifShrinkError(Exception):
    """带稳定错误码的业务异常 (cli/gui 依 code 决定是阻断还是提示)"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RasterMeta:
    path: Path
    width: int
    height: int
    count: int
    dtype: str
    nodata: float | None
    crs: str | None
    transform: object              # rasterio Affine; 类型留宽松以免 import rasterio 于类型检查期
    res_x: float
    res_y: float
    overviews: tuple = ()
    descriptions: tuple = ()
    colorinterp: tuple = ()


@dataclass(frozen=True)
class DownscalePlan:
    source_level: int              # 使用的概览倍率 (1 = 原分辨率)
    factor: int                    # 块内合并因子
    out_res: float                 # 实际输出分辨率 (米)
    out_width: int
    out_height: int
    sub_pixels: int                # 每个输出像元平均的源层像元数 = factor^2
    source_pixels: int             # 需读取的源层像元总数
    notes: tuple = field(default_factory=tuple)


def read_meta(path: str | Path) -> RasterMeta:
    """读栅格元数据 (含波段描述与 colorinterp —— 下游靠它们识别 NIR/RE)"""
    import rasterio

    p = Path(path)
    try:
        with rasterio.open(p) as s:
            return RasterMeta(
                path=p, width=int(s.width), height=int(s.height), count=int(s.count),
                dtype=s.dtypes[0], nodata=s.nodata,
                crs=str(s.crs) if s.crs else None, transform=s.transform,
                res_x=float(s.res[0]), res_y=float(s.res[1]),
                overviews=tuple(s.overviews(1) or ()),
                descriptions=tuple(s.descriptions or (None,) * int(s.count)),
                colorinterp=tuple(c.name for c in s.colorinterp),
            )
    except TifShrinkError:
        raise
    except Exception as e:                                      # noqa: BLE001
        raise TifShrinkError("OPEN_FAILED",
                             f"无法打开影像: {p.name} ({e.__class__.__name__}: {e})") from e


def default_output_path(src, out_res: float) -> Path:
    """默认输出路径: 源文件同目录 <stem>_<分辨率>m.tif (绝不写到源文件本身)"""
    from . import writer                     # 局部导入: 保持 core 的导入面轻量

    src = Path(src)
    return src.parent / f"{src.stem}_{writer.output_res_label(out_res)}m.tif"


def _level_pixels(meta: RasterMeta, level: int) -> int:
    """某一概览层的像元总数"""
    return math.ceil(meta.width / level) * math.ceil(meta.height / level)


def plan_downscale(meta: RasterMeta, target_m: float,
                   src_level_steps: int = C.SRC_LEVEL_STEPS,
                   sub_pixels_source_max: int = C.SUB_PIXELS_SOURCE_MAX) -> DownscalePlan:
    """目标分辨率 -> 可执行的降尺度方案"""
    if meta.crs is None:
        raise TifShrinkError("NO_CRS", "影像没有坐标系 (CRS), 无法生成处方图所需的矢量结果")

    if target_m < meta.res_x:
        raise TifShrinkError(
            "TARGET_TOO_FINE",
            f"目标分辨率 {target_m} m 比原图 {meta.res_x:.6f} m 还细, 本工具不做放大")

    ovr = sorted(meta.overviews)
    levels = [1, *ovr]
    cands = [lv for lv in ovr if meta.res_x * lv <= target_m * 1.001]
    level0 = max(cands) if cands else 1
    i0 = levels.index(level0)

    # 先取细 src_level_steps 级; 若源层像元超限则向更粗回退, 但绝不超过 i0
    steps = max(0, int(src_level_steps))
    i = max(0, i0 - steps)
    while i < i0 and _level_pixels(meta, levels[i]) > sub_pixels_source_max:
        i += 1
    level = levels[i]

    notes: list = []
    if i > max(0, i0 - steps):
        notes.append(f"为控制耗时, 源数据层退化到 level {level}"
                     f" (分辨率 {meta.res_x * level:.4f} m)")
    if _level_pixels(meta, level) > sub_pixels_source_max:
        notes.append(f"源层像元数仍超过上限 {sub_pixels_source_max:,}, "
                     f"已按最粗可用层处理, 耗时可能较长")
    if not ovr:
        notes.append("影像无概览, 将按原分辨率逐块读取, 大影像耗时较长")

    level_res = meta.res_x * level
    factor = max(1, int(round(target_m / level_res)))
    out_res = level_res * factor
    out_width = math.ceil(math.ceil(meta.width / level) / factor)
    out_height = math.ceil(math.ceil(meta.height / level) / factor)

    return DownscalePlan(
        source_level=int(level), factor=int(factor), out_res=float(out_res),
        out_width=int(out_width), out_height=int(out_height),
        sub_pixels=int(factor * factor),
        source_pixels=int(_level_pixels(meta, level)),
        notes=tuple(notes),
    )
