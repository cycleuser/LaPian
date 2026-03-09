"""
LaPian (拉片) — CLI & GUI tool for batch video transcoding with
hardware-accelerated encoding support.

Supports 4 presets: GIF, Android-compatible MP4, minimum-size MP4, audio-only.
Auto-detects available hardware encoders (NVENC, QSV, AMF, VAAPI, VideoToolbox)
with graceful fallback to software encoding.

Requires FFmpeg installed and available in PATH.
"""

__version__ = "1.3.4"

from .core import (
    TranscodeJob,
    BatchSummary,
    JobStatus,
    AdSegment,
    DeadvertResult,
    DeadvertSummary,
    run_transcode,
    run_batch,
    run_deadvert,
    detect_hw_encoders,
    probe_video,
    collect_input_files,
    build_output_path,
    check_ffmpeg,
    PRESET_NAMES,
    SUPPORTED_EXTENSIONS,
)
from .api import ToolResult, transcode, batch_transcode, probe_video as api_probe_video

__all__ = [
    "__version__",
    "TranscodeJob",
    "BatchSummary",
    "JobStatus",
    "AdSegment",
    "DeadvertResult",
    "DeadvertSummary",
    "run_transcode",
    "run_batch",
    "run_deadvert",
    "detect_hw_encoders",
    "probe_video",
    "collect_input_files",
    "build_output_path",
    "check_ffmpeg",
    "PRESET_NAMES",
    "SUPPORTED_EXTENSIONS",
    "ToolResult",
    "transcode",
    "batch_transcode",
    "api_probe_video",
]
