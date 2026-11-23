# tifshrink 打包说明

交付给用户的是**可执行文件**，用户不需要装 Python。

| 平台 | 产物 | 状态 |
|---|---|---|
| macOS | `影像压缩工具.app` + `tifshrink-cli` | **已实测**（本机构建并验证） |
| Windows | `影像压缩工具.exe` + `tifshrink-cli.exe` | 规格脚本就绪，由独立仓 `ltgrass/tifshrink` 的 GitHub Actions（`windows-latest`）构建 |

## macOS

```bash
pip install -r tifshrink/build/requirements-build.txt
bash tifshrink/build/build_macos.sh
```

产物在 `dist/`：`影像压缩工具.app`、`tifshrink-cli`、`影像压缩工具-macos.zip`（交付包，内含 `交付说明.txt`）。

- onedir（而非 onefile）形式：GDAL 的动态库在 onefile 下解压到临时目录容易出问题。
- **未做开发者签名**：用户首次打开需「右键 → 打开」（用户已确认接受此方式），`交付说明.txt` 里写了这一步。
- 打包会显式排除 `ricefert`/`rsbatch`/`sklearn`/`pandas`/`matplotlib`，这是包体积能保持在几十 MB 的关键。

## Windows

在 Windows 机器上于仓库根目录执行：

```bat
pip install -r tifshrink\build\requirements-build.txt
tifshrink\build\build_windows.bat
```

产物：`dist\影像压缩工具.exe`、`dist\tifshrink-cli.exe`（onefile）。

- 可执行文件**不能跨平台打包**：macOS 上产不出 Windows exe，反之亦然。
- 首次构建若报缺模块，把模块名补进 `tifshrink-windows.spec` 的 `hiddenimports`。
- 构建后请跑一次自检：`dist\tifshrink-cli.exe "某影像.tif" --target 0.5 --json`。

## 为什么同时打包一个 CLI

`tifshrink-cli` 有两个用途：① 打包后**不弹窗**就能验证冻结环境（GDAL / `proj_data` / rasterio 是否带齐），这是打包环节唯一可自动化的验收手段；② 售后排障时请用户跑一条命令把输出发回来，比让他描述界面现象可靠得多。

## 用户侧的两个前提

1. **影像要带坐标系**（GeoTIFF + CRS）：没有 CRS 的影像出不了处方图，工具会直接拒绝。
2. **把 `.tif` 与同名 `.ovr` 一起拷**：`.ovr` 是金字塔，带上它压缩快很多；不带也能压，只是要按全分辨率读一遍。
