# -*- coding: utf-8 -*-
"""打包入口 (命令行): 与 launch_gui.py 同理 —— 冻结后入口不能用相对导入。

命令行产物用于售后排障, 也是打包后唯一能不弹窗验证冻结环境的手段。
"""
from tifshrink.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
