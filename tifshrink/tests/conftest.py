# -*- coding: utf-8 -*-
"""测试前置: PROJ 数据目录必须在任何 rasterio 使用之前修正。

本机环境里若残留外部 PROJ_DATA/PROJ_LIB, 按 EPSG 构造 CRS 会报
"EPSG code is unknown"。修正实现见 tests/_projfix.py。
工具本体不需要这一步, 只有测试需要。
"""
from . import _projfix

_projfix.ensure_proj_data()
