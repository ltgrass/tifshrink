# -*- coding: utf-8 -*-
"""PROJ 数据目录修正 (仅独立仓使用: rsbatch 的等价精简实现)

主仓 (rice-fert-engine) 的 tests/conftest.py 直接复用 `rsbatch` 导入期执行的
projfix; 独立仓 (ltgrass/tifshrink) 没有 rsbatch, 只有测试需要这个修正, 所以在这里
放一份等价实现。

为什么需要: rasterio bundled 的 PROJ 与 proj.db 一一对应, 但 PROJ 优先读环境变量
PROJ_DATA / PROJ_LIB。若环境里串入另一个 conda/系统 PROJ, 按 EPSG 构造 CRS 会报
"EPSG code is unknown ... comes from another PROJ installation"。影像能正常打开
(源 CRS 写在 tif 头里, 不查库), 只在 EPSG 解析时炸, 极具迷惑性。

改动 rsbatch/projfix.py 时请同步本文件 (两处逻辑必须等价)。
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def bundled_proj_data() -> Path | None:
    """返回 rasterio 自带的 proj_data 目录 (含 proj.db), 找不到返回 None

    用 find_spec 定位而不是 import rasterio —— 后者可能已经触发 PROJ 初始化,
    改环境变量就来不及了。
    """
    try:
        spec = importlib.util.find_spec("rasterio")
    except Exception:                                          # noqa: BLE001
        return None
    if not spec or not spec.origin:
        return None
    d = Path(spec.origin).resolve().parent / "proj_data"
    return d if (d / "proj.db").is_file() else None


def ensure_proj_data() -> str | None:
    """把 PROJ_DATA/PROJ_LIB 指向 rasterio 自带数据目录; 返回实际使用的路径"""
    d = bundled_proj_data()
    if d is None:
        return os.environ.get("PROJ_DATA")
    os.environ["PROJ_DATA"] = str(d)
    os.environ["PROJ_LIB"] = str(d)
    return str(d)
