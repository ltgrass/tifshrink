# -*- coding: utf-8 -*-
"""界面纯函数: 输出路径、体积文案、提示文案

tkinter 窗口本身不写自动化测试(脆弱), 由人工验收 (计划 Task 6 Step 5):
可测的是全部"算出来的东西" —— 这里覆盖。
"""
from pathlib import Path

from tifshrink import core, gui


def _meta(**kw):
    base = dict(path=Path("DOM.tif"), width=66790, height=90235, count=3, dtype="uint8",
                nodata=0.0, crs="EPSG:32652", transform=None, res_x=0.004423748950957508,
                res_y=0.004423748950957508, overviews=(2, 4, 8, 16, 32, 64, 128),
                descriptions=("", "", ""), colorinterp=("gray", "gray", "gray"))
    base.update(kw)
    return core.RasterMeta(**base)


def test_suggest_output_path_uses_actual_resolution():
    assert gui.suggest_output_path("/tmp/DOM.tif", 0.4954599).name == "DOM_0.4955m.tif"


def test_format_bytes():
    assert gui.format_bytes(0) == "0.0 B"
    assert gui.format_bytes(3_040_000) == "2.9 MB"


def test_hints_flag_oversized_output():
    meta = _meta()
    plan = core.plan_downscale(meta, 0.5)
    hints = gui.build_hints(meta, plan, uncompressed_bytes=200 * 1024 * 1024)
    assert any("100" in h for h in hints)


def test_hints_flag_too_coarse_for_cell_size():
    meta = _meta()
    plan = core.plan_downscale(meta, 8.0)
    assert any("作业单元" in h for h in gui.build_hints(meta, plan, 1))


def test_hints_flag_fewer_than_four_bands():
    meta = _meta(count=3)
    plan = core.plan_downscale(meta, 0.5)
    assert any("波段" in h for h in gui.build_hints(meta, plan, 1))


def test_hints_flag_missing_overviews():
    meta = _meta(overviews=())
    plan = core.plan_downscale(meta, 0.5)
    assert any("概览" in h for h in gui.build_hints(meta, plan, 1))


def test_hints_empty_for_healthy_case():
    meta = _meta(width=5000, height=5000, count=4, overviews=(2, 4, 8))
    plan = core.plan_downscale(meta, 0.5)
    assert gui.build_hints(meta, plan, 1024) == []


def test_hints_surface_plan_notes():
    """源层因像元上限退化时必须在界面说明原因 (spec §4.2 step 4)"""
    meta = _meta()
    plan = core.plan_downscale(meta, 0.5, sub_pixels_source_max=10_000_000)
    assert plan.notes
    hints = gui.build_hints(meta, plan, 1024)
    assert any("退化" in h for h in hints)


def test_hints_no_overview_includes_time_estimate():
    """无概览的退化路径必须给耗时预估, 不能只说"较长" (spec §3.1 提示④)"""
    meta = _meta(width=40000, height=40000, overviews=())
    plan = core.plan_downscale(meta, 0.5)
    hints = gui.build_hints(meta, plan, 1024)
    overview_hint = [h for h in hints if "概览" in h]
    assert overview_hint and any(unit in overview_hint[0] for unit in ("秒", "分钟"))


def test_summary_lines_report_size_and_compression_note():
    meta = _meta()
    plan = core.plan_downscale(meta, 0.5)
    est = 3_040_000
    text = "\n".join(gui.summary_lines(meta, plan, est, src_bytes=8_821_812_022))
    assert "0.4955" in text and "2.9 MB" in text      # 实际输出分辨率与预计体积
    assert "1.5" in text and "2.5" in text            # deflate 后通常更小的说明
    assert "49 个细像元" in text
    assert "407" in text                              # 每个 10 m 作业单元含的像元数


def test_resolve_overwrite_asks_only_when_target_exists(tmp_path):
    target = tmp_path / "out.tif"
    asked = []
    assert gui.resolve_overwrite(target, lambda m: asked.append(m) or True) is False
    assert asked == []                                # 不存在就不该打扰用户
    target.write_text("x", encoding="utf-8")
    assert gui.resolve_overwrite(target, lambda m: asked.append(m) or True) is True
    assert asked and "覆盖" in asked[0]
    assert gui.resolve_overwrite(target, lambda m: False) is None   # 用户放弃
