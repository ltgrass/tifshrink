# -*- coding: utf-8 -*-
"""打包入口契约: PyInstaller 把入口脚本当 __main__ 执行, 入口**不能**用相对导入

`from . import config` 在冻结后必然报
"attempted relative import with no known parent package" —— 这个错误只在打包产物里
出现, 源码运行完全正常, 所以必须在打包前就用测试钉住:
按 PyInstaller 的方式执行每个 spec 声明的入口 (sys.path 含仓库根 + run_name='__main__')。
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "tifshrink" / "build"
SPECS = ["tifshrink-macos.spec", "tifshrink-cli.spec", "tifshrink-windows.spec"]
_ENTRY_RE = re.compile(r'os\.path\.join\(ROOT,\s*"tifshrink",\s*"([^"]+)"\)')


def _entries_of(spec: Path) -> list:
    return sorted(set(_ENTRY_RE.findall(spec.read_text(encoding="utf-8"))))


def _run_as_frozen(entry: str) -> subprocess.CompletedProcess:
    """复现冻结后的执行环境: 仓库根在 sys.path, 入口作为 __main__ 运行"""
    preamble = ("import tifshrink.gui as g\ng.main = lambda: 0\n" if "gui" in entry
                else "import tifshrink.cli as c\nc.main = lambda argv=None: 0\n")
    code = (f"import runpy, sys\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            f"{preamble}"
            f"sys.argv = [{entry!r}, '--help']\n"
            f"runpy.run_path({str(ROOT / 'tifshrink' / entry)!r}, run_name='__main__')\n")
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, cwd=ROOT)


@pytest.mark.parametrize("spec", SPECS)
def test_spec_has_at_least_one_entry(spec):
    assert _entries_of(BUILD / spec), f"{spec} 里找不到入口定义"


@pytest.mark.parametrize("spec", SPECS)
def test_entries_survive_frozen_execution(spec):
    for entry in _entries_of(BUILD / spec):
        r = _run_as_frozen(entry)
        assert r.returncode == 0, f"{spec} 入口 {entry} 冻结后执行失败:\n{r.stderr}"
        assert "relative import" not in r.stderr
