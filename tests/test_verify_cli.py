"""CLI 子命令测试"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.verify.cli import build_parser, run_verify_v10


def test_build_parser_has_required_args():
    """必填参数都在"""
    parser = build_parser()
    # 用 sys.argv 模拟
    args = parser.parse_args(["--limit", "30", "--days", "200"])
    assert args.limit == 30
    assert args.days == 200
    assert args.walk_forward is False
    assert args.json is False


def test_build_parser_limit_range_validation():
    """--limit 必须在 [10, 500]"""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--limit", "5"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--limit", "1000"])


def test_run_verify_v10_invokes_pipeline():
    """run_verify_v10 调用 pipeline"""
    with patch("modules.verify.cli.verify_v10_pipeline") as mock_pipeline:
        from modules.verify.pipeline import VerifyResult, AggregateMetrics

        mock_pipeline.return_value = VerifyResult(
            aggregate=AggregateMetrics(),
        )
        run_verify_v10(
            ts_codes=["000001.SZ"],
            days=250,
        )
        mock_pipeline.assert_called_once()
