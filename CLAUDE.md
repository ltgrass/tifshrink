# CLAUDE.md

本文件面向在本仓库工作的 Claude Code / 协作者，记录项目约定、架构不变量与容易踩的坑。
改动代码前请先读完「入口契约」与「数据流与不变量」两节。

## 项目概况

`tifshrink` 是一个独立开源小工具：把无人机拼出的超大 GeoTIFF 降分辨率压缩到可上传的体积。
交付形态是**单文件可执行程序**（Windows `.exe` / macOS `.app`），用户不需要安装 Python；
同时提供 CLI，用于打包后的自检与售后排障。

**依赖纪律（硬约束）**：运行时只允许依赖 `rasterio` + `numpy` + `tkinter`（标准库）。
不要引入 pandas / scikit-learn / matplotlib / requests 等。各 `.spec` 里的 `excludes`
正是为此而设 —— 产物体积从几十 MB 涨到几百 MB 的典型原因就是误引入了它们。

## 常用命令

```bash
# 测试（不需要图形环境；GUI 只测纯函数）
pytest tifshrink/tests -q

# 从源码运行
python -m tifshrink.gui
python -m tifshrink.cli 影像.tif --target 0.5 --json

# 本地打包
pip install -r tifshrink/build/requirements-build.txt
bash   tifshrink/build/build_macos.sh          # macOS
tifshrink\build\build_windows.bat              # Windows（仓库根目录执行）
```

## 入口契约（改动前必读）

`tifshrink/` **必须**是仓库根下的子目录，不能把包内容摊到仓库根。三个原因：

1. `launch_gui.py` / `launch_cli.py` 用绝对导入 `from tifshrink.gui import main`。
   PyInstaller 把入口脚本当 `__main__` 执行，入口内**不能**写相对导入
   （否则冻结后报 `attempted relative import with no known parent package`，
   而源码运行完全正常 —— 所以这个契约由 `tests/test_entrypoints.py` 在打包前锁住）。
2. 三个 `.spec` 用 `ROOT = os.path.join(SPECPATH, "..", "..")` 反推仓库根，
   再拼 `ROOT/tifshrink/launch_*.py` 作为入口。
3. `tests/test_entrypoints.py` 用 `Path(__file__).parents[2]` 定位仓库根，
   并用正则扫描 spec 里的 `os.path.join(ROOT, "tifshrink", ...)` 来发现入口。

新增打包入口时必须同时满足上述三点，否则 `test_entrypoints.py` 会失败。

## 数据流与不变量

```
core.read_meta ─► core.plan_downscale ─► downscale.downscale（分块） ─► writer.write_profile
```

改任何一环都要守住下面这些不变量（都有测试锁住）：

1. **分层选择**：输出网格取「分辨率仍细于 target 的最粗概览层 `L0`」；源数据层比 `L0`
   再细 `SRC_LEVEL_STEPS` 级，源层像元数超过 `SUB_PIXELS_SOURCE_MAX` 时向更粗回退，
   但**绝不粗于 `L0`**（否则输出会比用户要求更粗）。
2. **均值不是抽稀**：每个输出像元 = `factor × factor` 个细像元的盒均值。
   `aggregate.aggregate_box` 的运算顺序（`reshape → sum(float64) → 除以有效像元数`）
   是与下游实现逐点对齐的口径，**不要"优化"成别的写法**。
3. **nodata**：无效像元不参与均值；完全无效的输出像元写 nodata（不是 0）。
4. **dtype**：回写源 dtype，**只有整数类型才 `np.rint`**。对 float 源无条件取整会把
   float32 反射率整幅归零（0.34 → 0），而 dtype / nodata 元数据看起来完全正常。
5. **transform**：用**未四舍五入**的 `out_res` 计算，避免累计漂移。
6. **元数据保真**：`descriptions` 与 `colorinterp` 必须逐波段复制（rasterio 的 profile
   不携带它们）。空字符串要归一为 `None`，否则读-写-读不一致。
7. **落盘安全**：先写 `<dst>.partial`，成功后 `os.replace`。取消/失败保留 `.partial`，
   **不删除任何文件**；输出路径与源相同时拒绝（`SAME_PATH`）；已存在且未 `--force` 时
   拒绝（`OUTPUT_EXISTS`）。
8. **错误模型**：业务错误抛 `TifShrinkError(code, message)`；CLI 映射为退出码 2；
   GUI 按 `code` 决定弹窗还是只在状态栏提示（`CANCELLED` 不弹错误框）。

## 打包

- PyInstaller **不能跨平台交叉编译**：Windows 产物只能在 Windows 上打（CI 用
  `windows-latest`），macOS 产物在 macOS 上打。
- `proj_data` / `gdal_data` 必须用 `collect_data_files("rasterio", includes=[...])` 收进去。
  漏了会在「按 EPSG 构造 CRS」时报 `EPSG code is unknown`，而影像仍能正常打开 ——
  极具迷惑性（源 CRS 写在 tif 头里，不查库）。
- `hiddenimports` 里那份 rasterio 子模块清单是扫描 Cython 扩展字面引用得到的并集，
  漏一个冻结后就 `ModuleNotFoundError`。补 `tkinter.ttk` 之类的新增项也加在这里。
- macOS 用 onedir + `BUNDLE`；Windows 用 onefile（把 `binaries`/`datas` 交给 `EXE`
  即为单文件形式）。**不要**给 `EXE` 传 `onefile=True` —— 没有这个参数。
- 两个平台的产物都**未签名**，README 里已说明用户首次打开的放行步骤。

## CI

`.github/workflows/build-windows.yml`：`workflow_dispatch` / push `main` / PR / `v*` tag 触发。
顺序：装依赖 → `pytest` → PyInstaller → **冻结环境自检** → 7z 打 zip → artifact / Release。

自检必须"真跑"：用打出来的 `tifshrink-cli.exe` 压缩一张 `EPSG:32652` 的测试图并断言
`out_res == 0.5`。只测 exe 能启动是验不到 `proj_data` 的 —— 只有写盘时才会解析 EPSG。

## 测试策略

- 无显示环境也能跑：GUI 只测纯函数（`test_gui.py` 不创建 Tk 窗口）。
- Windows 上 `chmod` 不改变目录写权限 → `test_unwritable_output_dir_raises_write_failed`
  自动跳过。**属预期行为，不要当 bug 修。**
- `tests/conftest.py` 会在导入 rasterio 之前调用 `tests/_projfix.py`，把 `PROJ_DATA`
  指向 rasterio 自带的 `proj_data`（见「常见坑」第 1 条）；新增的测试若直接
  `import rasterio`，应确保这一步已经跑过。
- 新增行为请补测试；打包相关改动至少跑一次 `test_entrypoints.py`。

## 常见坑

1. **conda 的 PROJ 串味**：环境里残留外部 `PROJ_DATA` 时，按 EPSG 构造 CRS 会报
   `EPSG code is unknown ... comes from another PROJ installation`。
   `tests/conftest.py` 会在导入 rasterio 之前把 `PROJ_DATA`/`PROJ_LIB` 指向 rasterio
   自带的 `proj_data`（实现见 `tests/_projfix.py`）。任何在测试里 import rasterio 的
   新代码都应确保该修正已生效。
2. **中文文件名与 zip**：CI 用 `7z -mcu=on` 打交付 zip，Windows 资源管理器才不会把
   `影像压缩工具.exe` 显示成乱码；`Compress-Archive` 在这点上有坑。
3. **onefile 首次启动慢**：会解压到临时目录，属正常现象。
4. **不要加并行读取**：单幅影像按块串行处理，性能靠概览层控制；并行会与进度/取消逻辑纠缠。
5. **Windows CI 的 stdout 编码**：GitHub runner 上 Python 的 stdout 是 cp1252（不是 UTF-8），
   往 stdout 打印中文会 `UnicodeEncodeError`。因此自检脚本只输出 ASCII；CLI 的 `--json`
   在编码失败时退回 `ensure_ascii=True`（合法 JSON，`\uXXXX` 转义不影响机器消费）。

## 发布流程

```bash
git tag v1.0.0 && git push origin v1.0.0
```

CI 构建、自检，并把 zip 附到 Release。版本号同时写在
`tifshrink/build/tifshrink-macos.spec` 的 `CFBundleShortVersionString` 与 `README` 的下载说明里，
发版时记得一起改。

## 修改代码前的自检清单

- [ ] 没有引入新的第三方依赖（只 rasterio + numpy + 标准库）
- [ ] `pytest tifshrink/tests -q` 全绿
- [ ] 入口 / spec 的路径推导未被破坏（`test_entrypoints.py` 覆盖）
- [ ] 改动 `aggregate.py` / `downscale.py` 时，逐点一致性断言仍成立
- [ ] 面向用户的文案（GUI 提示、`build/交付说明.txt`）已同步更新
