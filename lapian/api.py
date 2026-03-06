"""
LaPian - Unified Python API.

Provides ToolResult-based wrappers for programmatic usage
and agent integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ToolResult:
    """Standardised return type for all LaPian API functions."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
        }


def transcode(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    preset: str = "minsize",
    crf: int | None = None,
    audio_bitrate: str | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
    fps: float | None = None,
    dry_run: bool = False,
) -> ToolResult:
    """Transcode a video file using an FFmpeg preset.

    Parameters
    ----------
    input_path : str or Path
        Input video file.
    output_path : str, Path, or None
        Output file path. Auto-generated if None.
    preset : str
        Preset name: gif, android, minsize, or audio.
    crf : int or None
        CRF quality value override.
    audio_bitrate : str or None
        Audio bitrate override (e.g. '128k').
    max_width : int or None
        Max output width.
    max_height : int or None
        Max output height.
    fps : float or None
        Output frame rate.
    dry_run : bool
        If True, build commands but don't execute.

    Returns
    -------
    ToolResult
        With data containing output path and job details.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        return ToolResult(success=False, error=f"File not found: {input_path}")

    try:
        from . import __version__
        from .core import (
            TranscodeJob,
            run_transcode,
            build_output_path,
            PRESET_NAMES,
        )

        if preset not in PRESET_NAMES:
            return ToolResult(
                success=False,
                error=f"Invalid preset: {preset!r}. Valid: {PRESET_NAMES}",
            )

        if output_path is None:
            output_path = build_output_path(str(input_path), preset)
        else:
            output_path = str(output_path)

        options = {}
        if crf is not None:
            options["crf"] = crf
        if audio_bitrate:
            options["audio_bitrate"] = audio_bitrate
        if max_width:
            options["max_width"] = max_width
        if max_height:
            options["max_height"] = max_height
        if fps:
            options["fps"] = fps

        job = TranscodeJob(
            input_path=str(input_path),
            output_path=output_path,
            preset=preset,
            options=options,
        )

        ok = run_transcode(job, dry_run=dry_run)

        return ToolResult(
            success=ok,
            data={
                "input_path": str(input_path),
                "output_path": output_path,
                "preset": preset,
                "status": job.status.value if hasattr(job.status, "value") else str(job.status),
                "error_msg": job.error_msg or None,
            },
            metadata={
                "dry_run": dry_run,
                "version": __version__,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def batch_transcode(
    input_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    preset: str = "minsize",
    recursive: bool = False,
    dry_run: bool = False,
) -> ToolResult:
    """Batch-transcode all video files in a directory.

    Parameters
    ----------
    input_dir : str or Path
        Directory containing video files.
    output_dir : str, Path, or None
        Output directory. Defaults to input_dir.
    preset : str
        Preset name: gif, android, minsize, or audio.
    recursive : bool
        Scan subdirectories.
    dry_run : bool
        Preview without executing.

    Returns
    -------
    ToolResult
        With data containing batch results and summary.
    """
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        return ToolResult(success=False, error=f"Not a directory: {input_dir}")

    try:
        from . import __version__
        from .core import (
            TranscodeJob,
            run_batch,
            collect_input_files,
            build_output_path,
            PRESET_NAMES,
        )

        if preset not in PRESET_NAMES:
            return ToolResult(
                success=False,
                error=f"Invalid preset: {preset!r}. Valid: {PRESET_NAMES}",
            )

        files = collect_input_files(str(input_dir), recursive=recursive)
        if not files:
            return ToolResult(
                success=True,
                data={"jobs": [], "success": 0, "failed": 0},
                metadata={"input_dir": str(input_dir)},
            )

        jobs = []
        for f in files:
            out = build_output_path(f, preset)
            if output_dir:
                out = str(Path(output_dir) / Path(out).name)
            jobs.append(TranscodeJob(
                input_path=f,
                output_path=out,
                preset=preset,
            ))

        summary = run_batch(jobs, dry_run=dry_run)

        results = []
        for j in jobs:
            results.append({
                "input": j.input_path,
                "output": j.output_path,
                "status": j.status.value if hasattr(j.status, "value") else str(j.status),
                "error": j.error_msg or None,
            })

        return ToolResult(
            success=summary.failed == 0 if hasattr(summary, "failed") else True,
            data={
                "jobs": results,
                "success": summary.ok if hasattr(summary, "ok") else len(results),
                "failed": summary.failed if hasattr(summary, "failed") else 0,
            },
            metadata={
                "input_dir": str(input_dir.resolve()),
                "preset": preset,
                "dry_run": dry_run,
                "version": __version__,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def probe_video(input_path: str | Path) -> ToolResult:
    """Probe a video file and return its metadata.

    Parameters
    ----------
    input_path : str or Path
        Path to the video file.

    Returns
    -------
    ToolResult
        With data containing video metadata (duration, resolution, codecs, etc.).
    """
    input_path = Path(input_path)
    if not input_path.exists():
        return ToolResult(success=False, error=f"File not found: {input_path}")

    try:
        from . import __version__
        from .core import probe_video as _probe

        info = _probe(str(input_path))

        return ToolResult(
            success=True,
            data=info,
            metadata={
                "input_path": str(input_path),
                "version": __version__,
            },
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))
