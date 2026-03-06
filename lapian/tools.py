"""
LaPian - OpenAI function-calling tool definitions.

Provides TOOLS list and dispatch() for LLM agent integration.
"""

from __future__ import annotations

import json
from typing import Any

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lapian_transcode",
            "description": (
                "Transcode a video file using an FFmpeg preset. Supports "
                "GIF, Android-compatible MP4, minimum-size MP4, and "
                "audio-only extraction. Auto-detects hardware encoders."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_path": {
                        "type": "string",
                        "description": "Path to the input video file.",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output file path (auto-generated if omitted).",
                    },
                    "preset": {
                        "type": "string",
                        "enum": ["gif", "android", "minsize", "audio"],
                        "description": "Transcoding preset.",
                        "default": "minsize",
                    },
                    "crf": {
                        "type": "integer",
                        "description": "CRF quality value override (lower = better quality).",
                    },
                    "audio_bitrate": {
                        "type": "string",
                        "description": "Audio bitrate override (e.g. '128k').",
                    },
                    "max_width": {
                        "type": "integer",
                        "description": "Maximum output width in pixels.",
                    },
                    "max_height": {
                        "type": "integer",
                        "description": "Maximum output height in pixels.",
                    },
                    "fps": {
                        "type": "number",
                        "description": "Output frame rate.",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Build commands but don't execute.",
                        "default": False,
                    },
                },
                "required": ["input_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lapian_batch_transcode",
            "description": (
                "Batch-transcode all video files in a directory using "
                "an FFmpeg preset."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_dir": {
                        "type": "string",
                        "description": "Directory containing video files.",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (default: same as input).",
                    },
                    "preset": {
                        "type": "string",
                        "enum": ["gif", "android", "minsize", "audio"],
                        "description": "Transcoding preset.",
                        "default": "minsize",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Scan subdirectories.",
                        "default": False,
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Preview without executing.",
                        "default": False,
                    },
                },
                "required": ["input_dir"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lapian_probe_video",
            "description": (
                "Probe a video file and return its metadata including "
                "duration, resolution, codecs, bitrate, and frame rate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_path": {
                        "type": "string",
                        "description": "Path to the video file.",
                    },
                },
                "required": ["input_path"],
            },
        },
    },
]


def dispatch(name: str, arguments: dict[str, Any] | str) -> dict:
    """Dispatch a tool call to the appropriate API function."""
    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    if name == "lapian_transcode":
        from .api import transcode

        result = transcode(**arguments)
        return result.to_dict()

    if name == "lapian_batch_transcode":
        from .api import batch_transcode

        result = batch_transcode(**arguments)
        return result.to_dict()

    if name == "lapian_probe_video":
        from .api import probe_video

        result = probe_video(**arguments)
        return result.to_dict()

    raise ValueError(f"Unknown tool: {name}")
