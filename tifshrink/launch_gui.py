# -*- coding: utf-8 -*-
"""打包入口 (图形界面): PyInstaller 把入口脚本当顶层模块 __main__ 执行,
而包内部用的是相对导入 (from . import config), 冻结后必然 ImportError。
所以入口必须单独一个文件、只用绝对导入。

自检: tifshrink/tests/test_entrypoints.py 会按 PyInstaller 的方式执行本文件。
"""
from tifshrink.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
