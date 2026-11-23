# -*- coding: utf-8 -*-
"""tifshrink - 无人机影像降分辨率压缩工具 (上传 OBS 前的预处理)

只依赖 rasterio + numpy, 不 import 本仓库的 ricefert/rsbatch:
用户拿到的可执行文件才不会被 sklearn/pandas 等无关依赖撑大。
"""
