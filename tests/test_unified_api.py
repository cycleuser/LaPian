"""
Comprehensive tests for LaPian unified API, tools, and CLI flags.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestToolResult:
    def test_success(self):
        from lapian.api import ToolResult
        r = ToolResult(success=True, data={"output_path": "/tmp/out.mp4"})
        assert r.success is True

    def test_failure(self):
        from lapian.api import ToolResult
        r = ToolResult(success=False, error="ffmpeg not found")
        assert r.error == "ffmpeg not found"

    def test_to_dict(self):
        from lapian.api import ToolResult
        d = ToolResult(success=True, data="ok", metadata={"v": "1.3"}).to_dict()
        assert d["success"] is True
        assert d["data"] == "ok"

    def test_default_metadata_isolation(self):
        from lapian.api import ToolResult
        r1 = ToolResult(success=True)
        r2 = ToolResult(success=True)
        r1.metadata["a"] = 1
        assert "a" not in r2.metadata


class TestTranscodeAPI:
    def test_missing_file(self):
        from lapian.api import transcode
        result = transcode("/no/such/file.mp4")
        assert result.success is False
        assert "File not found" in result.error

    def test_invalid_preset(self):
        from lapian.api import transcode
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            result = transcode(f.name, preset="invalid_preset")
            assert result.success is False
            assert "Invalid preset" in result.error

    def test_accepts_path_object(self):
        from lapian.api import transcode
        result = transcode(Path("/nonexistent.mp4"))
        assert result.success is False

    def test_valid_presets_accepted(self):
        from lapian.api import transcode
        for preset in ["gif", "android", "minsize", "audio"]:
            with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
                result = transcode(f.name, preset=preset, dry_run=True)
                # May fail on ffmpeg but should not fail on preset validation
                assert "Invalid preset" not in (result.error or "")


class TestBatchTranscodeAPI:
    def test_invalid_directory(self):
        from lapian.api import batch_transcode
        result = batch_transcode("/nonexistent/dir")
        assert result.success is False
        assert "Not a directory" in result.error

    def test_empty_directory(self):
        from lapian.api import batch_transcode
        with tempfile.TemporaryDirectory() as d:
            result = batch_transcode(d, preset="minsize")
            assert result.success is True
            assert result.data["success"] == 0
            assert result.data["failed"] == 0

    def test_invalid_preset(self):
        from lapian.api import batch_transcode
        with tempfile.TemporaryDirectory() as d:
            result = batch_transcode(d, preset="bogus")
            assert result.success is False
            assert "Invalid preset" in result.error


class TestProbeVideoAPI:
    def test_missing_file(self):
        from lapian.api import probe_video
        result = probe_video("/no/such/file.mp4")
        assert result.success is False
        assert "File not found" in result.error

    def test_accepts_path(self):
        from lapian.api import probe_video
        result = probe_video(Path("/nonexistent.mkv"))
        assert result.success is False


class TestToolsSchema:
    def test_tools_count(self):
        from lapian.tools import TOOLS
        assert len(TOOLS) == 3

    def test_tool_names(self):
        from lapian.tools import TOOLS
        names = [t["function"]["name"] for t in TOOLS]
        assert "lapian_transcode" in names
        assert "lapian_batch_transcode" in names
        assert "lapian_probe_video" in names

    def test_structure(self):
        from lapian.tools import TOOLS
        for tool in TOOLS:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            params = func["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            for req in params["required"]:
                assert req in params["properties"]

    def test_transcode_presets_enum(self):
        from lapian.tools import TOOLS
        for t in TOOLS:
            if t["function"]["name"] == "lapian_transcode":
                presets = t["function"]["parameters"]["properties"]["preset"]["enum"]
                assert set(presets) == {"gif", "android", "minsize", "audio"}


class TestToolsDispatch:
    def test_unknown_tool(self):
        from lapian.tools import dispatch
        with pytest.raises(ValueError):
            dispatch("bad", {})

    def test_dispatch_transcode_missing(self):
        from lapian.tools import dispatch
        result = dispatch("lapian_transcode", {"input_path": "/no.mp4"})
        assert isinstance(result, dict)
        assert result["success"] is False

    def test_dispatch_probe_missing(self):
        from lapian.tools import dispatch
        result = dispatch("lapian_probe_video", {"input_path": "/no.mp4"})
        assert result["success"] is False

    def test_dispatch_batch_empty_dir(self):
        from lapian.tools import dispatch
        with tempfile.TemporaryDirectory() as d:
            result = dispatch("lapian_batch_transcode", {"input_dir": d})
            assert result["success"] is True

    def test_dispatch_json_string(self):
        from lapian.tools import dispatch
        args = json.dumps({"input_path": "/no.mp4"})
        result = dispatch("lapian_transcode", args)
        assert isinstance(result, dict)


class TestCLIFlags:
    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "lapian"] + list(args),
            capture_output=True, text=True, timeout=15,
        )

    def test_version_flag(self):
        r = self._run_cli("-V")
        assert r.returncode == 0
        assert "lapian" in r.stdout.lower()

    def test_help_has_unified_flags(self):
        r = self._run_cli("--help")
        assert "--json" in r.stdout
        assert "--quiet" in r.stdout or "-q" in r.stdout
        assert "--verbose" in r.stdout or "-v" in r.stdout


class TestPackageExports:
    def test_version(self):
        import lapian
        assert hasattr(lapian, "__version__")
        assert lapian.__version__ == "1.3.2"

    def test_toolresult(self):
        from lapian import ToolResult
        assert callable(ToolResult)

    def test_transcode(self):
        from lapian import transcode
        assert callable(transcode)

    def test_batch_transcode(self):
        from lapian import batch_transcode
        assert callable(batch_transcode)

    def test_core_exports(self):
        from lapian import TranscodeJob, JobStatus, PRESET_NAMES
        assert TranscodeJob is not None
        assert JobStatus is not None
        assert isinstance(PRESET_NAMES, (list, tuple, set, dict))
