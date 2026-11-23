# -*- coding: utf-8 -*-
"""命令行入口: 也是排障与脚本调用的接口, --json 供上游程序消费"""
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tifshrink import cli


@pytest.fixture
def src(tmp_path):
    p = tmp_path / "big.tif"
    prof = dict(driver="GTiff", width=400, height=400, count=4, dtype="uint16", nodata=0,
                crs="EPSG:32652", transform=from_origin(500000, 5000000, 0.05, 0.05))
    with rasterio.open(p, "w", **prof) as d:
        d.write(np.full((4, 400, 400), 1000, dtype="uint16"))
        d.descriptions = ("NIR(mock)", "RedEdge(mock)", "Red", "Green")
    return p


def test_cli_writes_default_output_next_to_source(src, capsys):
    rc = cli.main([str(src), "--target", "0.5"])
    assert rc == 0 and (src.parent / "big_0.5m.tif").exists()


def test_cli_json_output_is_machine_readable(src, capsys):
    rc = cli.main([str(src), "--target", "0.5", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["out_res"] == 0.5 and payload["dst"].endswith(".tif")


def test_cli_returns_2_on_too_fine_target(src, capsys):
    rc = cli.main([str(src), "--target", "0.001"])
    assert rc == 2 and "分辨率" in capsys.readouterr().err
