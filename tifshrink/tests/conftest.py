# -*- coding: utf-8 -*-
"""测试共用的导入前置: PROJ 数据目录必须在任何 rasterio 使用之前修正。

主仓 (rice-fert-engine) 有 rsbatch, 直接借它导入期的 projfix 副作用;
独立仓 (ltgrass/tifshrink) 没有 rsbatch, 用 tests/_projfix.py 的等价实现。

本机 conda 环境里存在串味的 PROJ, 不修正时按 EPSG 构造 CRS 会报
"EPSG code is unknown"。工具本体不依赖任何 PROJ 修正, 只有测试需要。
"""
import importlib.util

if importlib.util.find_spec("rsbatch") is not None:
    import rsbatch  # noqa: F401  主仓: projfix 在 rsbatch 导入期执行
else:                                                        # 独立仓
    from . import _projfix

    _projfix.ensure_proj_data()
