# -*- mode: python ; coding: utf-8 -*-
"""Windows 打包规格 (onefile) —— 需在 **Windows 机器** 上执行, 不能在 macOS 交叉打包

构建: 在 Windows 上于仓库根目录执行
    pip install -r tifshrink\\build\\requirements-build.txt
    pyinstaller --noconfirm tifshrink\\build\\tifshrink-windows.spec

CI: 独立仓 ltgrass/tifshrink 的 .github/workflows/build-windows.yml 在
    windows-latest 上跑同一组命令 (含"用产物真压一张测试图"的自检), 无需本地 Windows。

产物: dist\\影像压缩工具.exe  (单文件, 双击即用)
      dist\\tifshrink-cli.exe (命令行版, 售后排障)
注意: 本规格是照 macOS 实测经验写的, Windows 上首次构建如报缺模块, 把缺失的模块名
      加进 hiddenimports 即可 —— 常见的是 tkinter 的 ttk。
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
ENTRY_GUI = os.path.join(ROOT, "tifshrink", "launch_gui.py")
ENTRY_CLI = os.path.join(ROOT, "tifshrink", "launch_cli.py")
# 只收数据目录 (proj_data/gdal_data), 否则 GDAL 会被当数据与二进制各收一份
datas = collect_data_files("rasterio", includes=["proj_data/**", "gdal_data/**"])
binaries = collect_dynamic_libs("rasterio")

gui = Analysis(
    [ENTRY_GUI],
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
    excludes=["matplotlib", "pandas", "sklearn", "scipy", "pytest"],
    noarchive=False,
)
# 注意: 不要给 EXE 传 onefile=True —— PyInstaller 的单文件形式由"把 binaries/datas
# 交给 EXE"这一写法本身决定, 并不存在 onefile 这个参数, 多传一个未识别的 kwarg
# 在不同版本上行为不一致 (新版可能直接 TypeError)。本规格即为 onefile。
gui_pyz = PYZ(gui.pure)
gui_exe = EXE(
    gui_pyz, gui.scripts, gui.binaries, gui.datas, [],
    name="影像压缩工具", debug=False, strip=False, upx=False,
    console=False, icon=None,
)

cli = Analysis(
    [ENTRY_CLI],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["rasterio._base", "rasterio._env", "rasterio._err", "rasterio._example",
                   "rasterio._features", "rasterio._filepath", "rasterio._fill",
                   "rasterio._io", "rasterio._path", "rasterio._transform",
                   "rasterio._version", "rasterio._vsiopener", "rasterio._warp",
                   "rasterio.control", "rasterio.coords", "rasterio.crs",
                   "rasterio.drivers", "rasterio.dtypes", "rasterio.enums",
                   "rasterio.env", "rasterio.errors", "rasterio.path",
                   "rasterio.profiles", "rasterio.rpc", "rasterio.sample",
                   "rasterio.transform", "rasterio.vrt", "rasterio.windows"],
    excludes=["matplotlib", "pandas", "sklearn", "scipy", "pytest", "tkinter"],
    noarchive=False,
)
cli_pyz = PYZ(cli.pure)
cli_exe = EXE(
    cli_pyz, cli.scripts, cli.binaries, cli.datas, [],
    name="tifshrink-cli", debug=False, strip=False, upx=False,
    console=True, icon=None,
)
