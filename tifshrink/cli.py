# -*- coding: utf-8 -*-
"""tifshrink.cli - 无界面入口 (排障与脚本调用)

    python -m tifshrink.cli SRC [--target 0.5] [--out DST] [--force] [--json]

约定: 进度打到 stderr, 结果打到 stdout —— --json 时 stdout 只有一行 JSON,
可直接被上游程序消费。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config as C
from . import core, downscale, writer
from .core import TifShrinkError

EXIT_OK = 0
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tifshrink.cli",
        description="把超大 GeoTIFF 降分辨率压缩到可上传的体积 (上传前预处理)")
    p.add_argument("src", help="源影像路径 (GeoTIFF, 需带坐标系)")
    p.add_argument("--target", type=float, default=C.DEFAULT_TARGET_M,
                   help=f"目标分辨率(米), 默认 {C.DEFAULT_TARGET_M}")
    p.add_argument("--out", default=None, help="输出路径 (默认 '源同名_<分辨率>m.tif')")
    p.add_argument("--force", action="store_true", help="输出已存在时覆盖")
    p.add_argument("--json", action="store_true", help="结果以 JSON 打到 stdout")
    return p


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    src = Path(args.src)

    def progress(done: int, total: int) -> None:
        if total and (done == total or done % max(1, total // 10) == 0):
            print(f"\r  进度 {done}/{total} 块", end="", file=sys.stderr, flush=True)

    try:
        meta = core.read_meta(src)
        plan = core.plan_downscale(meta, args.target)
        dst = Path(args.out) if args.out else core.default_output_path(src, plan.out_res)
        for note in plan.notes:
            print(f"[提示] {note}", file=sys.stderr)
        res = downscale.downscale(src, dst, args.target, overwrite=args.force,
                                 progress=progress)
    except TifShrinkError as e:
        print(f"[错误] {e.message}", file=sys.stderr)
        return EXIT_ERROR

    print("", file=sys.stderr)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        mb = res["bytes_out"] / 1048576
        print(f"完成: {res['dst']}")
        print(f"  {res['out_width']}x{res['out_height']} 像元, "
              f"分辨率 {res['out_res']} m (源层 level {res['source_level']}, "
              f"每输出像元 {res['sub_pixels']} 个细像元均值)")
        print(f"  体积 {mb:.2f} MB, 耗时 {res['elapsed_sec']} s")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
