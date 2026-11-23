# -*- mode: python ; coding: utf-8 -*-
"""macOS 打包规格: 影像压缩工具.app (图形界面)

构建: bash tifshrink/build/build_macos.sh
产物: dist/影像压缩工具.app  (onedir 形式, 再压缩成 zip 交付)

只依赖 rasterio + numpy + tkinter: 不 import ricefert/rsbatch, 因此
PyInstaller 不会把 sklearn/pandas 拖进来 (那是体积从 ~80MB 涨到 300MB 的原因)。
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
ENTRY = os.path.join(ROOT, "tifshrink", "launch_gui.py")

# rasterio 自带的 proj_data / gdal_data 必须一起打包, 否则按 EPSG 构造 CRS 会报
# "EPSG code is unknown" (与服务端 rsbatch/projfix.py 修的是同一个坑)。
# 这里**只收数据目录**: rasterio 包里还有个 .dylibs/ (约 40MB, GDAL 在其中),
# 用 collect_data_files("rasterio") 不加 includes 会把 .dylibs/* 与 *.so 也当数据收进
# Resources/, 同时 collect_dynamic_libs 又把它们收进 Frameworks/ —— 同一份 GDAL 存两遍,
# 实测产物从 ~77MB 涨到 143MB。
datas = collect_data_files("rasterio", includes=["proj_data/**", "gdal_data/**"])
binaries = collect_dynamic_libs("rasterio")

# rasterio 的 Cython 扩展在 C 层按名字互相引用, PyInstaller 的静态分析看不到,
# 漏一个冻结后就报 ModuleNotFoundError (实测依次漏过 sample, vrt, _features)。
# 这份清单是扫描 rasterio/*.so 里全部 "rasterio.<name>" 字面引用得到的并集;
# 刻意不含 rio/plot/stack/tools (会拖进 click 与 matplotlib)。
RASTERIO_SUBMODULES = [
    "rasterio._base", "rasterio._env", "rasterio._err", "rasterio._example",
    "rasterio._features", "rasterio._filepath", "rasterio._fill", "rasterio._io",
    "rasterio._path", "rasterio._transform", "rasterio._version",
    "rasterio._vsiopener", "rasterio._warp", "rasterio.control", "rasterio.coords",
    "rasterio.crs", "rasterio.drivers", "rasterio.dtypes", "rasterio.enums",
    "rasterio.env", "rasterio.errors", "rasterio.path", "rasterio.profiles",
    "rasterio.rpc", "rasterio.sample", "rasterio.transform", "rasterio.vrt",
    "rasterio.windows",
]

a = Analysis(
    [ENTRY],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    # rasterio 的 Cython 扩展在 C 层引用这些子模块 (静态分析看不到), 漏一个冻结后就报
    # ModuleNotFoundError。清单来自扫描 rasterio/*.so 里 "rasterio.<name>" 的字面引用。
    hiddenimports=RASTERIO_SUBMODULES + [
        "tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["ricefert", "rsbatch", "matplotlib", "pandas", "sklearn", "scipy", "pytest"],
    noarchive=False,
)

# 注意: 不要"优化"掉 rasterio hook 塞进 datas 的 GDAL 动态库 (rasterio/.dylibs/*)。
# rasterio 的扩展模块用 @rpath 到包根目录找 libgdal, hook 把 .dylibs 压平到根正是
# 为了让这个查找成立; 实测滤掉它们后, 冻结产物会报
# "Library not loaded: @rpath/libgdal.35.3.9.3.dylib"。
# 代价是同一份 GDAL 也作为 binaries 进了一次, 产物约 143MB —— 这是可运行的最小代价。
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="影像压缩工具",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="影像压缩工具",
)
app = BUNDLE(
    coll,
    name="影像压缩工具.app",
    icon=None,
    bundle_identifier="com.ricefert.tifshrink",
    info_plist={
        "CFBundleName": "影像压缩工具",
        "CFBundleDisplayName": "影像压缩工具",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.15",
        # 未签名分发: 用户首次需"右键 -> 打开" (用户已确认接受)
        "LSApplicationCategoryType": "public.app-category.utilities",
    },
)
