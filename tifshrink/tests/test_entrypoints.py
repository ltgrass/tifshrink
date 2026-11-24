# -*- coding: utf-8 -*-
"""打包入口契约: PyInstaller 把入口脚本当 __main__ 执行, 入口**不能**用相对导入

`from . import config` 在冻结后必然报
"attempted relative import with no known parent package" —— 这个错误只在打包产物里
出现, 源码运行完全正常, 所以必须在打包前就用测试钉住:
按 PyInstaller 的方式执行每个 spec 声明的入口 (sys.path 含仓库根 + run_name='__main__')。
"""
import ast
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


def _literal_strings(node, named_lists):
    """取 spec 里 hiddenimports 参数的字符串常量 (支持 Name / List / List + List)"""
    if isinstance(node, ast.List):
        return [e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    if isinstance(node, ast.Name):
        return named_lists.get(node.id, [])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal_strings(node.left, named_lists) + _literal_strings(node.right, named_lists)
    return []


def _hiddenimports_of(spec: Path) -> list[set[str]]:
    """返回 spec 中每个 Analysis(hiddenimports=...) 的模块名集合"""
    tree = ast.parse(spec.read_text(encoding="utf-8"))
    named_lists = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    named_lists[target.id] = _literal_strings(node.value, named_lists)
    sets = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "Analysis"):
            for kw in node.keywords:
                if kw.arg == "hiddenimports":
                    sets.append(set(_literal_strings(kw.value, named_lists)))
    return sets


@pytest.mark.parametrize("spec", SPECS)
def test_spec_hiddenimports_include_rasterio_serde(spec):
    hidden = _hiddenimports_of(BUILD / spec)
    assert hidden, f"{spec} 里找不到 Analysis(hiddenimports=...)"
    for names in hidden:
        assert "rasterio.serde" in names, (
            f"{spec} 的 hiddenimports 漏了 rasterio.serde: "
            "rasterio 1.4.4 的 _base.pyx 在 C 层 import 它, 冻结后必然缺模块"
        )


def test_build_requirements_pin_rasterio():
    req = (BUILD / "requirements-build.txt").read_text(encoding="utf-8")
    assert "rasterio==1.4.4" in req, (
        "hiddenimports 清单与 rasterio 版本绑定, 不要放开版本"
    )
