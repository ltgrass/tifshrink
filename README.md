# tifshrink · 影像压缩工具

把无人机拼好的超大 GeoTIFF 降分辨率压缩到能上传的体积（上传 OBS 前的预处理）。
工具只做压缩：不上传、不改几何、不做任何农艺计算。

- 运行时**只依赖 `rasterio` + `numpy` + `tkinter`**，不 import 任何其它内部包；
  这是为了让交付给用户的可执行文件不被 sklearn/pandas 撑大。
- 降采样的数学必须与服务端 `rsbatch/raster.py` 保持一致（逐点相等的断言在主仓）。

本仓库从 `rice-fert-engine` 主仓的 `tifshrink/` 独立而来，独立管理版本与发布。

## 仓库结构

```
.
├── .github/workflows/build-windows.yml   # Windows exe 构建 (GitHub Actions)
├── tifshrink/                            # 包本体
│   ├── gui.py  cli.py  core.py  downscale.py  writer.py  aggregate.py  compare.py  config.py
│   ├── launch_gui.py  launch_cli.py      # PyInstaller 入口 (必须是绝对导入)
│   ├── tests/
│   └── build/                            # 打包规格与脚本
└── README.md
```

`launch_*.py` 用 `from tifshrink.gui import main`，三个 `.spec` 用
`ROOT = SPECPATH/../..` 反推仓库根，`tests/test_entrypoints.py` 用 `parents[2]`
定位仓库根 —— **所以 `tifshrink/` 必须是仓库根下的一个子目录，不能摊平**。

## 构建

### Windows（推荐用 CI）

推一个 `v*` tag（或手动触发 `build-windows` workflow），Actions 会：

1. `pip install -r tifshrink/build/requirements-build.txt`
2. `pytest tifshrink/tests -q`
3. `pyinstaller tifshrink/build/tifshrink-windows.spec`（onefile，产出 GUI + CLI 两个 exe）
4. 用打出来的 `tifshrink-cli.exe` 真压一张 `EPSG:32652` 测试图，断言 `out_res == 0.5`
   （这一步才真正验证打包进去的 GDAL / proj_data 可用）
5. 打 `tifshrink-windows.zip` 并上传 artifact；tag 时附到 Release

本地构建（在 Windows 机器上，仓库根目录）：

```bat
pip install -r tifshrink\build\requirements-build.txt
tifshrink\build\build_windows.bat
```

### macOS

```bash
pip install -r tifshrink/build/requirements-build.txt
bash tifshrink/build/build_macos.sh
```

产物在 `dist/`：`影像压缩工具.app`、`tifshrink-cli`、`影像压缩工具-macos.zip`。

## 测试

```bash
pytest tifshrink/tests -q
```

本仓库没有 `rsbatch`，以下用例会**自动 skip**（它们的一致性护栏在主仓运行）：
`test_matches_rsbatch_aggregate_pointwise`、`test_detect_band_map_identical_before_and_after`、
`test_read_meta_reads_real_mock_image`（依赖主仓的 `data/mock/`）。
Windows 上额外 skip `test_unwritable_output_dir_raises_write_failed`（chmod 在 Windows
不改变目录写权限）。

`tifshrink-cli` 有两个用途：① 打包后不弹窗就能验证冻结环境；② 售后排障时请用户
跑一条命令把输出发回来：

```bat
tifshrink-cli.exe "影像.tif" --target 0.5 --json
```

## 交付注意

- 可执行文件**不能跨平台打包**：macOS 上产不出 Windows exe，反之亦然。
- 未做代码签名：macOS 首次打开需「右键 → 打开」（或系统设置里的「仍要打开」），
  Windows 首次运行可能被 SmartScreen 拦一次。
- 用户侧前提：影像必须带坐标系（GeoTIFF + CRS）；把同名 `.ovr` 金字塔一起拷会快很多。
