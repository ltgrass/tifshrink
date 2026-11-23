#!/usr/bin/env bash
# macOS 打包: 影像压缩工具.app + tifshrink-cli, 并压缩成交付 zip
#
# 用法: bash tifshrink/build/build_macos.sh
# 前置: pip install -r tifshrink/build/requirements-build.txt
#
# 注意: 本脚本**不删除任何文件** (PyInstaller 用 --noconfirm 覆盖自己的输出目录)。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
NAME="影像压缩工具-macos"

# 每次构建输出到**新的带时间戳目录**: PyInstaller 的 --noconfirm 不会清理已存在的
# .app, 复用同一目录会把两轮产物叠加进去 (实测 .app 从 77MB 涨到 143MB, Frameworks
# 与 Resources 各存一份 libgdal/rasterio)。新目录从根上避免叠加, 也不需要删除任何文件。
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$ROOT/dist/macos-$STAMP"
WORK="$OUT/_work"          # 工作目录也收进本次构建目录, 不往仓库根堆 PyInstaller 中间产物
mkdir -p "$OUT"
APP="$OUT/影像压缩工具.app"
CLI="$OUT/tifshrink-cli"

cd "$ROOT"

echo "== 构建 GUI (.app) -> $OUT =="
pyinstaller --noconfirm --distpath "$OUT" --workpath "$WORK" "$HERE/tifshrink-macos.spec"

echo "== 构建 CLI (打包自检/售后用) =="
pyinstaller --noconfirm --distpath "$OUT" --workpath "$WORK" "$HERE/tifshrink-cli.spec"

echo "== 打包自检 (用包内的 CLI 真跑一次, 不弹窗) =="
CHECK="$OUT/_selfcheck"
mkdir -p "$CHECK"
python - "$CHECK" <<'PYCODE'
import importlib.util
import sys
if importlib.util.find_spec("rsbatch") is not None:
    import rsbatch                 # 主仓: 借其导入期的 projfix (本机 conda PROJ 会串味)
else:                              # 独立仓: 没有 rsbatch, 用 tests/_projfix.py 的等价实现
    sys.path.insert(0, "tifshrink/tests")
    import _projfix
    _projfix.ensure_proj_data()
import numpy as np
import rasterio
from rasterio.transform import from_origin
p = sys.argv[1] + "/in.tif"
with rasterio.open(p, "w", driver="GTiff", width=400, height=400, count=4,
                   dtype="uint16", nodata=0, crs="EPSG:32652",
                   transform=from_origin(500000, 5000000, 0.05, 0.05)) as d:
    d.write(np.full((4, 400, 400), 1000, dtype="uint16"))
    d.descriptions = ("NIR", "RedEdge", "Red", "Green")
PYCODE
"$CLI" "$CHECK/in.tif" --target 0.5 --out "$CHECK/out.tif" --json
echo "自检通过 (冻结环境可用: GDAL / proj_data / rasterio 均已带上)"

echo "== 打包交付 zip =="
cp "$HERE/交付说明.txt" "$OUT/交付说明.txt"
(cd "$OUT" && zip -qry "$NAME.zip" "影像压缩工具.app" "tifshrink-cli" "交付说明.txt")

echo
echo "完成 (交付这个 zip 即可):"
echo "  $OUT/$NAME.zip"
echo "  $APP"
echo "  $CLI"
du -sh "$APP" "$OUT/$NAME.zip"
echo
echo "提示: dist/ 下每次构建会新建一个 macos-<时间戳> 目录;"
echo "      确认新产物可用后, 旧目录请自行清理 (本脚本不删任何文件)。"
