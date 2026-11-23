# -*- mode: python ; coding: utf-8 -*-
"""命令行产物 (售后排障 + 打包自检)

与 GUI 共用同一份依赖收集。它的存在有两个理由:
  1) 打包后能**不弹窗**地验证冻结环境 (GDAL/proj_data/rasterio 是否都带齐了);
  2) 出问题时可以请用户跑一条命令把输出发回来, 比让用户描述界面现象可靠得多。
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
ENTRY = os.path.join(ROOT, "tifshrink", "launch_cli.py")

# 只收数据目录, 避免 GDAL 在 Resources/ 与 Frameworks/ 各存一份 (见 macos spec 的说明)
datas = collect_data_files("rasterio", includes=["proj_data/**", "gdal_data/**"])
binaries = collect_dynamic_libs("rasterio")

a = Analysis(
    [ENTRY],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    # Cython 扩展在 C 层引用这些子模块 (静态分析看不到), 见 macos spec 的说明
    hiddenimports=["rasterio._base", "rasterio._env", "rasterio._err", "rasterio._example",
                   "rasterio._features", "rasterio._filepath", "rasterio._fill",
                   "rasterio._io", "rasterio._path", "rasterio._transform",
                   "rasterio._version", "rasterio._vsiopener", "rasterio._warp",
                   "rasterio.control", "rasterio.coords", "rasterio.crs",
                   "rasterio.drivers", "rasterio.dtypes", "rasterio.enums",
                   "rasterio.env", "rasterio.errors", "rasterio.path",
                   "rasterio.profiles", "rasterio.rpc", "rasterio.sample",
                   "rasterio.transform", "rasterio.vrt", "rasterio.windows"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["ricefert", "rsbatch", "matplotlib", "pandas", "sklearn", "scipy",
              "pytest", "tkinter"],
    noarchive=False,
)
# 不要滤掉 rasterio hook 收进来的 .dylibs (见 macos spec 的说明: @rpath 需要它们)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="tifshrink-cli",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
