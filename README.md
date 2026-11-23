# tifshrink · 影像压缩工具

**把无人机拼好的超大 GeoTIFF 降分辨率压缩到可上传的体积。**

一个依赖极轻（`rasterio` + `numpy` + `tkinter`）的小工具：图形界面与命令行双入口，
可打包成单文件可执行程序，用户无需安装 Python。工具只做压缩——不上传、不改几何、
不做任何业务计算。

> tifshrink downsamples huge drone-survey GeoTIFFs to an upload-friendly resolution.
> Dependency-light (rasterio + numpy + tkinter), shipped as a single-file executable
> for Windows and macOS, with both a GUI and a CLI.

## 特性

- **图形界面 + 命令行**：双击即用的窗口，以及便于脚本调用与排障的 CLI
- **分块流式处理**：内存占用与影像大小无关，GB 级影像也能压
- **金字塔感知**：优先使用影像自带的 `.ovr` 概览，只读必要的那一层
- **nodata 安全**：无效像元不参与均值，输出对应像元仍写 nodata
- **元数据保真**：CRS、波段描述、colorinterp 原样带到输出，下游可直接识别波段
- **体积可控**：deflate + 512 分块，输出通常比未压缩上界再小 1.5~2.5 倍
- **零额外依赖**：不引入 pandas / sklearn / matplotlib，打包产物只有几十 MB

## 安装 / 运行

### 已打包的可执行文件

从 [Releases](https://github.com/ltgrass/tifshrink/releases) 下载：

- **Windows**：`tifshrink-windows.zip`，解压后双击「影像压缩工具.exe」
- **macOS**：`影像压缩工具-macos.zip`，首次打开需右键 →「打开」（未做代码签名）

### 从源码运行

需要 Python 3.9+ 与 rasterio：

```bash
pip install rasterio numpy
python -m tifshrink.gui                              # 图形界面
python -m tifshrink.cli 影像.tif --target 0.5 --json  # 命令行
```

## 命令行

```
python -m tifshrink.cli SRC [--target 米] [--out 输出路径] [--force] [--json]
```

| 参数 | 说明 |
|---|---|
| `SRC` | 源影像（GeoTIFF，**必须带坐标系**） |
| `--target` | 目标分辨率（米），默认 `0.5` |
| `--out` | 输出路径，默认「源同名_<分辨率>m.tif」 |
| `--force` | 输出已存在时覆盖 |
| `--json` | 结果以一行 JSON 打到 stdout（进度走 stderr），便于脚本消费 |

退出码：`0` 成功，`2` 失败（原因打在 stderr）。

## 构建

可执行文件**不能跨平台打包**：macOS 上产不出 Windows exe，反之亦然。

### Windows（推荐用 CI）

推一个 `v*` tag，或手动触发 `build-windows` workflow。CI 会先跑单测，再用打出来的
exe 真压一张测试图验证冻结环境（GDAL / proj_data）可用；产物在 Actions 的 artifact 里，
打 tag 时自动附到 Release。

本地构建（Windows，仓库根目录）：

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
pip install -r tifshrink/build/requirements-build.txt
pytest tifshrink/tests -q
```

测试覆盖降尺度规划、分块聚合（含 uint16 大批量累加不溢出）、nodata 语义、输出元数据，
以及两个打包入口的冻结契约（`tests/test_entrypoints.py` 会在打包前按 PyInstaller 的方式
执行入口脚本）。Windows CI 上有一条"只读目录"用例会自动跳过 —— Windows 的 `chmod`
不改变目录写权限，属预期行为。

## 工作原理

```
read_meta ──► plan_downscale ──► 分块流式读取 ──► k×k 盒均值 ──► 写 GeoTIFF
```

1. **定输出网格**：取「分辨率仍细于目标」的最粗一级概览作为基准层 `L0`；
2. **定源数据层**：比 `L0` 再细几级 —— 每个输出像元由多个细像元的**均值**得到，
   而不是抽稀采一个点；源层像元数超限时向更粗回退，但绝不粗于 `L0`；
3. **分块处理**：按块读取后用一次 `reshape(h,f,w,f).sum(axis=(1,3))` 完成 `k×k` 合并，
   峰值内存与影像大小无关；
4. **落盘**：先写 `<dst>.partial`，成功后原子替换 —— 取消或失败不会留下看似正常的半成品。

## 精度与使用建议

- 默认 `0.5 m` 对下游结果影响极小：在带 1 m 尺度冠层纹理（5% 起伏）的合成影像上实测，
  平均偏差 0.3%，单元级 P95 偏差 0.9%。
- **不要把输出分辨率设到接近作业尺度**（例如 10 m）：那等于「先把反射率平均、再做反演」，
  结果会明显不同。界面会对这种用法给出「压缩过狠」的提示。
- 影像必须带 CRS，没有坐标系的影像会被直接拒绝。
- 把同名 `.ovr` 金字塔与影像放在一起会快很多（没有也能压，只是慢一些）。

## 项目结构

```
.
├── .github/workflows/build-windows.yml   # Windows 构建（GitHub Actions）
├── tifshrink/
│   ├── core.py        元数据读取与降尺度规划（纯函数）
│   ├── downscale.py   端到端分块流式降尺度
│   ├── aggregate.py   k×k 盒均值（nodata 不参与）
│   ├── writer.py      输出 profile 与波段元数据
│   ├── compare.py     栅格对齐与偏差统计（对照实验用）
│   ├── config.py      策略常量
│   ├── cli.py / gui.py               两个入口的实现
│   ├── launch_cli.py / launch_gui.py PyInstaller 入口
│   ├── tests/
│   └── build/         打包规格与脚本
└── README.md
```

> `tifshrink/` 必须是仓库根下的一个子目录（不能把内容摊到根）：入口脚本用
> `from tifshrink.gui import main`，三个 `.spec` 用 `SPECPATH/../..` 反推仓库根，
> `tests/test_entrypoints.py` 用 `parents[2]` 定位仓库根。

## 已知限制

- 只支持带坐标系的 GeoTIFF；其它格式会明确报错而不是静默出错。
- 未做代码签名：macOS 首次打开需右键 →「打开」，Windows 可能被 SmartScreen 拦一次。
- Windows 的 onefile 产物首次启动会解压到临时目录，比后续启动慢几秒。
- 不做并行读取：单幅影像按块串行处理，耗时由概览层控制。

## 发布

```bash
git tag v1.0.0
git push origin v1.0.0
```

CI 会构建、自检，并把 zip 附到对应的 Release。

## 许可

本项目采用 [Apache License 2.0](LICENSE)，Copyright 2026 ltgrass。

可以自由使用、修改、分发（含商业用途）；分发时需保留版权与许可声明，修改过的文件需注明改动。
完整条款见 [LICENSE](LICENSE)。

## 反馈

欢迎提 [Issue](https://github.com/ltgrass/tifshrink/issues)。报告问题时请附上 CLI 的完整输出：

```bash
tifshrink-cli 影像.tif --target 0.5 --json
```
