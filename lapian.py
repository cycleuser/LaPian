#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaPian (拉片) — CLI & GUI tool for batch video transcoding with
hardware-accelerated encoding support.

Supports 4 presets: GIF, Android-compatible MP4, minimum-size MP4, audio-only.
Auto-detects available hardware encoders (NVENC, QSV, AMF, VAAPI, VideoToolbox)
with graceful fallback to software encoding.

Requires FFmpeg installed and available in PATH.
"""

import argparse
import json
import locale
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

__version__ = "1.3.0"

# ============================================================================
# Section 1: Constants & i18n
# ============================================================================

def _detect_lang() -> str:
    """Detect system language. Returns 'zh' for Chinese, 'en' otherwise."""
    try:
        lang = locale.getlocale()[0] or ""
    except Exception:
        lang = ""
    if not lang:
        lang = os.environ.get("LANG", "") or os.environ.get("LANGUAGE", "")
    return "zh" if lang.startswith("zh") else "en"

_LANG = _detect_lang()

_STRINGS = {
    "en": {
        "add_files": "Add Files",
        "add_directory": "Add Directory",
        "clear_list": "Clear List",
        "file_queue": "File Queue",
        "options": "Options",
        "preset": "Preset:",
        "output_dir": "Output Dir:",
        "hw_encoder": "HW Encoder:",
        "detecting": "Detecting...",
        "crf": "CRF:",
        "gif_fps": "GIF FPS:",
        "max_width": "Max Width:",
        "audio_fmt": "Audio Fmt:",
        "recursive": "Recursive",
        "dry_run": "Dry Run",
        "verbose": "Verbose",
        "encoder": "Encoder:",
        "progress": "Progress",
        "file": "File:",
        "overall": "Overall:",
        "start": "Start Transcoding",
        "cancel": "Cancel",
        "log": "Log",
        "no_files_title": "No Files",
        "no_files_msg": "Please add files or directories first.",
        "batch_complete_title": "Batch Complete",
        "batch_complete": "Batch complete!",
        "done": "Done",
        "failed": "Failed",
        "skipped": "Skipped",
        "time_elapsed": "Time",
        "failed_files": "Failed files",
        "starting_batch": "Starting batch: preset={preset}, output={output}",
        "found_files": "Found {count} video file(s).",
        "no_video_found": "No supported video files found!",
        "cancel_requested": "Cancellation requested...",
        "hw_detected": "HW encoders: {encoders}",
        "no_hw": "No HW encoders found, using software.",
        "ffmpeg_not_found": "FFmpeg not found!",
        "none_sw_only": "None (software only)",
        "items": "{count} item(s)",
        "dir_prefix": "[DIR]",
        "select_video": "Select Video Files",
        "select_dir": "Select Directory",
        "select_output": "Select Output Directory",
        "video_files": "Video files",
        "all_files": "All files",
        "hw_detect_cli": "Hardware encoders detected: {encoders}",
        "no_hw_cli": "No hardware encoders detected, using software encoding.",
        "no_video_cli": "ERROR: No supported video files found.",
        "found_cli": "Found {count} video file(s).",
        "batch_summary": "Batch complete: {done} done, {failed} failed, {skipped} skipped ({elapsed:.1f}s total)",
        "failed_files_cli": "Failed files:",
        # -- UI extras --
        "about": "About",
        "about_text": (
            "LaPian (拉片) v{version}\n\n"
            "Batch video transcoder with hardware-accelerated encoding.\n"
            "CLI & GUI. Supports GIF, Android MP4, min-size MP4,\n"
            "and audio extraction.\n\n"
            "https://github.com/cycleuser/LaPian"
        ),
        "resolution": "Resolution:",
        "bitrate": "Bitrate:",
        "video_fps": "Video FPS:",
        # -- Deadvert --
        "deadvert": "Remove Ads (Deadvert)",
        "deadvert_method": "Detection Method:",
        "deadvert_audio": "Audio Fingerprint",
        "deadvert_video": "Video Frame Hash",
        "deadvert_min_dur": "Min Duration (s):",
        "deadvert_detecting": "Detecting ad segments...",
        "deadvert_extracting": "Extracting fingerprints: {current}/{total}",
        "deadvert_correlating": "Comparing videos: {current}/{total}",
        "deadvert_found": "Found {count} ad segment(s) in {videos} video(s)",
        "deadvert_no_ads": "No ad segments detected.",
        "deadvert_trimming": "Trimming: {current}/{total}",
        "deadvert_confirm_title": "Confirm Ad Removal",
        "deadvert_proceed": "Proceed",
        "deadvert_cancel_trim": "Cancel",
        "deadvert_segment": "{start} -> {end} ({duration}s)",
        "deadvert_need_multiple": "Deadvert requires at least 2 videos for cross-referencing.",
        "deadvert_dep_fpcalc": (
            "fpcalc (chromaprint) not found. Install it:\n"
            "  Ubuntu/Debian: sudo apt install libchromaprint-tools\n"
            "  macOS: brew install chromaprint\n"
            "  Windows: download from https://acoustid.org/chromaprint"
        ),
        "deadvert_dep_pillow": (
            "Pillow and/or imagehash not found. Install with:\n"
            "  pip install Pillow imagehash"
        ),
        "deadvert_total_removed": "Total ad time removed: {time:.1f}s",
        "deadvert_report_header": "Detected ad segments:",
        "deadvert_report_video": "  Video: {name}",
        "deadvert_report_seg": "    Ad {n}: {start} -> {end} ({duration:.1f}s) [in {count} videos]",
        "deadvert_confirm_prompt": "Proceed with trimming? [Y/n]: ",
        "deadvert_skipped_no_audio": "Skipping {name}: no audio track (audio method).",
        "deadvert_suggest_video": "All videos lack audio. Consider using --deadvert-method video.",
        "deadvert_video_all_ad": "Skipping {name}: entire video appears to be an ad.",
        "deadvert_no_change": "No ads found in {name}, copying original.",
        "detect_only": "Detection only (no trim)",
    },
    "zh": {
        "add_files": "添加文件",
        "add_directory": "添加目录",
        "clear_list": "清空列表",
        "file_queue": "文件队列",
        "options": "选项",
        "preset": "预设:",
        "output_dir": "输出目录:",
        "hw_encoder": "硬件编码:",
        "detecting": "检测中...",
        "crf": "CRF:",
        "gif_fps": "GIF帧率:",
        "max_width": "最大宽度:",
        "audio_fmt": "音频格式:",
        "recursive": "递归子目录",
        "dry_run": "仅预览",
        "verbose": "详细日志",
        "encoder": "编码器:",
        "progress": "进度",
        "file": "文件:",
        "overall": "总进度:",
        "start": "开始转码",
        "cancel": "取消",
        "log": "日志",
        "no_files_title": "没有文件",
        "no_files_msg": "请先添加文件或目录。",
        "batch_complete_title": "批处理完成",
        "batch_complete": "批处理完成!",
        "done": "完成",
        "failed": "失败",
        "skipped": "跳过",
        "time_elapsed": "耗时",
        "failed_files": "失败文件",
        "starting_batch": "开始批处理: 预设={preset}, 输出={output}",
        "found_files": "找到 {count} 个视频文件。",
        "no_video_found": "未找到支持的视频文件!",
        "cancel_requested": "正在取消...",
        "hw_detected": "硬件编码器: {encoders}",
        "no_hw": "未检测到硬件编码器，使用软件编码。",
        "ffmpeg_not_found": "未找到FFmpeg!",
        "none_sw_only": "无 (仅软件编码)",
        "items": "{count} 个项目",
        "dir_prefix": "[目录]",
        "select_video": "选择视频文件",
        "select_dir": "选择目录",
        "select_output": "选择输出目录",
        "video_files": "视频文件",
        "all_files": "所有文件",
        "hw_detect_cli": "检测到硬件编码器: {encoders}",
        "no_hw_cli": "未检测到硬件编码器，使用软件编码。",
        "no_video_cli": "错误: 未找到支持的视频文件。",
        "found_cli": "找到 {count} 个视频文件。",
        "batch_summary": "批处理完成: {done} 个完成, {failed} 个失败, {skipped} 个跳过 (共 {elapsed:.1f} 秒)",
        "failed_files_cli": "失败文件:",
        # -- UI extras --
        "about": "关于",
        "about_text": (
            "LaPian (拉片) v{version}\n\n"
            "批量视频转码工具，支持硬件加速编码。\n"
            "命令行与图形界面。支持GIF、Android MP4、\n"
            "最小体积MP4、音频提取。\n\n"
            "https://github.com/cycleuser/LaPian"
        ),
        "resolution": "分辨率:",
        "bitrate": "码率:",
        "video_fps": "视频帧率:",
        # -- Deadvert --
        "deadvert_method": "检测方法:",
        "deadvert_audio": "音频指纹",
        "deadvert_video": "视频帧哈希",
        "deadvert_min_dur": "最短时长(秒):",
        "deadvert_detecting": "正在检测广告片段...",
        "deadvert_extracting": "提取指纹: {current}/{total}",
        "deadvert_correlating": "比对视频: {current}/{total}",
        "deadvert_found": "在 {videos} 个视频中找到 {count} 个广告片段",
        "deadvert_no_ads": "未检测到广告片段。",
        "deadvert_trimming": "裁剪中: {current}/{total}",
        "deadvert_confirm_title": "确认去广告",
        "deadvert_proceed": "继续",
        "deadvert_cancel_trim": "取消",
        "deadvert_segment": "{start} -> {end} ({duration}秒)",
        "deadvert_need_multiple": "去广告需要至少2个视频进行交叉比对。",
        "deadvert_dep_fpcalc": (
            "未找到 fpcalc (chromaprint)，请安装:\n"
            "  Ubuntu/Debian: sudo apt install libchromaprint-tools\n"
            "  macOS: brew install chromaprint\n"
            "  Windows: 从 https://acoustid.org/chromaprint 下载"
        ),
        "deadvert_dep_pillow": (
            "未找到 Pillow 和/或 imagehash，请安装:\n"
            "  pip install Pillow imagehash"
        ),
        "deadvert_total_removed": "共去除广告时间: {time:.1f}秒",
        "deadvert_report_header": "检测到的广告片段:",
        "deadvert_report_video": "  视频: {name}",
        "deadvert_report_seg": "    广告{n}: {start} -> {end} ({duration:.1f}秒) [出现在{count}个视频中]",
        "deadvert_confirm_prompt": "是否继续裁剪? [Y/n]: ",
        "deadvert_skipped_no_audio": "跳过 {name}: 无音频轨道 (音频指纹方法)。",
        "deadvert_suggest_video": "所有视频均无音频轨道，建议使用 --deadvert-method video。",
        "deadvert_video_all_ad": "跳过 {name}: 整个视频疑似广告。",
        "deadvert_no_change": "{name} 未发现广告，复制原文件。",
        "detect_only": "仅检测(不裁剪)",
    },
}

def _t(key: str, **kwargs) -> str:
    """Get translated string for current language."""
    s = _STRINGS.get(_LANG, _STRINGS["en"]).get(key, _STRINGS["en"].get(key, key))
    if kwargs:
        return s.format(**kwargs)
    return s

SUPPORTED_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv",
    ".wmv", ".ts", ".m4v", ".3gp", ".mpg", ".mpeg",
    ".vob", ".ogv", ".m2ts", ".mts", ".f4v", ".rm", ".rmvb",
})

PRESET_NAMES = ("gif", "android", "minsize", "audio")

DEFAULT_OUTPUT_DIR = "./transcoded"

H264_CHAIN = [
    "h264_nvenc", "h264_qsv", "h264_amf",
    "h264_vaapi", "h264_videotoolbox", "libx264",
]

HEVC_CHAIN = [
    "hevc_nvenc", "hevc_qsv", "hevc_amf",
    "hevc_vaapi", "hevc_videotoolbox", "libx265",
]

KNOWN_ENCODERS = set(H264_CHAIN + HEVC_CHAIN + ["libmp3lame", "aac", "libvpx"])

log = logging.getLogger("lapian")

# ============================================================================
# Section 2: FFmpeg Detection & Hardware Probe
# ============================================================================

_hw_encoder_cache: Optional[dict] = None


def check_ffmpeg() -> tuple:
    """Check that ffmpeg and ffprobe are available. Returns their paths."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg not found in PATH.\n"
            "Install instructions:\n"
            "  Ubuntu/Debian: sudo apt install ffmpeg\n"
            "  macOS:         brew install ffmpeg\n"
            "  Windows:       https://ffmpeg.org/download.html\n"
            "  Arch Linux:    sudo pacman -S ffmpeg"
        )
    if not ffprobe:
        raise RuntimeError(
            "ffprobe not found in PATH. It usually ships with FFmpeg.\n"
            "Please reinstall FFmpeg to include ffprobe."
        )
    try:
        r = subprocess.run(
            [ffmpeg, "-version"], capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        version_line = r.stdout.split("\n")[0] if r.stdout else "unknown"
        log.info("FFmpeg found: %s", version_line)
    except Exception as e:
        raise RuntimeError(f"FFmpeg found but failed to run: {e}")
    return ffmpeg, ffprobe


def detect_hw_encoders() -> dict:
    """Detect available hardware encoders by parsing ffmpeg -encoders output."""
    global _hw_encoder_cache
    if _hw_encoder_cache is not None:
        return _hw_encoder_cache

    cache = {enc: False for enc in KNOWN_ENCODERS}
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            m = re.match(r"^\s*[A-Z.]+\s+(\S+)", line)
            if m:
                name = m.group(1)
                if name in cache:
                    cache[name] = True
    except Exception as e:
        log.warning("Failed to detect encoders: %s", e)

    _hw_encoder_cache = cache
    return cache


def probe_video(path: str) -> dict:
    """Probe a video file with ffprobe and return metadata."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        data = json.loads(r.stdout)
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))
        size_bytes = int(fmt.get("size", 0))

        width = height = fps = 0
        has_audio = False
        video_codec = audio_codec = ""

        for s in data.get("streams", []):
            if s.get("codec_type") == "video" and not width:
                width = int(s.get("width", 0))
                height = int(s.get("height", 0))
                video_codec = s.get("codec_name", "")
                r_fps = s.get("r_frame_rate", "0/1")
                try:
                    num, den = r_fps.split("/")
                    fps = round(int(num) / max(int(den), 1), 2)
                except (ValueError, ZeroDivisionError):
                    fps = 0
            elif s.get("codec_type") == "audio":
                has_audio = True
                audio_codec = s.get("codec_name", "")

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "has_audio": has_audio,
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "size_bytes": size_bytes,
        }
    except Exception as e:
        log.warning("Failed to probe %s: %s", path, e)
        return {}


def select_encoder(
    chain: list, available: dict, override: Optional[str] = None
) -> str:
    """Select the best available encoder from the chain."""
    if override:
        if available.get(override, False):
            return override
        log.warning(
            "Requested encoder '%s' not available, falling back to auto-detect",
            override,
        )
    for enc in chain:
        if available.get(enc, False):
            return enc
    return chain[-1]


# ============================================================================
# Section 3: Preset Definitions & Command Builders
# ============================================================================


def _get_hw_quality_flags(
    encoder: str, crf: int, bitrate: Optional[str] = None,
) -> list:
    """Return encoder-specific quality flags.

    If bitrate is set (e.g. "2M", "500k"), use ABR mode instead of CRF/CQ.
    """
    if bitrate:
        # Average bitrate mode for all encoders
        flags = ["-b:v", bitrate]
        if encoder == "libx264":
            flags = ["-preset", "slow"] + flags
        elif encoder == "libx265":
            flags = ["-preset", "slow"] + flags + [
                "-x265-params", "log-level=error"]
        elif "nvenc" in encoder:
            flags = ["-preset", "p4", "-rc", "vbr"] + flags
        elif "qsv" in encoder:
            flags = ["-preset", "slow"] + flags
        elif "amf" in encoder:
            flags = ["-quality", "balanced"] + flags
        return flags

    # CRF / constant quality mode
    if encoder == "libx264":
        return ["-preset", "slow", "-crf", str(crf)]
    elif encoder == "libx265":
        return ["-preset", "slow", "-crf", str(crf),
                "-x265-params", "log-level=error"]
    elif "nvenc" in encoder:
        return ["-preset", "p4", "-cq", str(crf), "-rc", "vbr"]
    elif "qsv" in encoder:
        return ["-preset", "slow", "-global_quality", str(crf)]
    elif "amf" in encoder:
        return ["-quality", "balanced", "-qp_i", str(crf),
                "-qp_p", str(crf)]
    elif "vaapi" in encoder:
        return ["-qp", str(crf)]
    elif "videotoolbox" in encoder:
        q = max(1, min(100, 100 - crf * 2))
        return ["-q:v", str(q)]
    return ["-crf", str(crf)]


_RESOLUTION_MAP = {
    "2160p": (3840, 2160),
    "1440p": (2560, 1440),
    "1080p": (1920, 1080),
    "720p":  (1280, 720),
    "480p":  (854,  480),
    "360p":  (640,  360),
    "240p":  (426,  240),
}

RESOLUTION_CHOICES = list(_RESOLUTION_MAP.keys())
FPS_CHOICES = [60, 30, 25, 24, 15]


def _build_scale_filter(
    width: Optional[int] = None,
    cap_height: Optional[int] = None,
    resolution: Optional[str] = None,
) -> list:
    """Build a -vf scale filter string. Returns [] if no scaling needed.

    resolution: e.g. "720p", "1080p" or "1280x720".
    width: max width, height auto-calculated.
    cap_height: max height cap.
    """
    filters = []
    if resolution:
        # Look up friendly name first (e.g. "720p")
        wh = _RESOLUTION_MAP.get(resolution.lower().strip())
        if wh:
            w, h = wh
        else:
            # Fallback: parse "WIDTHxHEIGHT"
            parts = resolution.lower().replace("x", ":").split(":")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                w, h = int(parts[0]), int(parts[1])
            else:
                return filters
        filters.append(
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:-1:-1:color=black"
        )
        return filters
    if width:
        filters.append(f"scale={width}:-2")
    elif cap_height:
        filters.append(f"scale=-2:'min({cap_height},ih)'")
    return filters


def build_gif_commands(
    input_path: str, output_path: str,
    fps: int = 10, width: int = 480, **kwargs,
) -> list:
    """Build two-pass GIF commands. Returns list of (cmd, description) tuples."""
    palette_path = os.path.join(
        tempfile.gettempdir(), f"palette_{uuid.uuid4().hex[:8]}.png"
    )
    vf_base = f"fps={fps},scale={width}:-1:flags=lanczos"

    cmd1 = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(input_path),
        "-vf", f"{vf_base},palettegen=stats_mode=diff",
        "-update", "1",
        str(palette_path),
    ]
    cmd2 = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(input_path),
        "-i", str(palette_path),
        "-lavfi",
        f"{vf_base} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
        str(output_path),
    ]
    return [(cmd1, "Generating palette", palette_path),
            (cmd2, "Encoding GIF", None)]


def build_android_command(
    input_path: str, output_path: str,
    encoder: str = "libx264", crf: int = 23,
    width: Optional[int] = None,
    resolution: Optional[str] = None,
    bitrate: Optional[str] = None,
    video_fps: Optional[int] = None,
    **kwargs,
) -> list:
    """Build Android-compatible MP4 command."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(input_path),
        "-c:v", encoder,
    ]
    cmd.extend(_get_hw_quality_flags(encoder, crf, bitrate=bitrate))

    if encoder == "libx264":
        cmd.extend(["-profile:v", "baseline", "-level:v", "3.1"])

    vf_parts = _build_scale_filter(width=width, resolution=resolution)
    if video_fps:
        vf_parts.append(f"fps={video_fps}")
    if vf_parts:
        cmd.extend(["-vf", ",".join(vf_parts)])
    elif video_fps:
        cmd.extend(["-r", str(video_fps)])

    cmd.extend([
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart",
        str(output_path),
    ])
    return [(cmd, "Encoding Android MP4", None)]


def build_minsize_command(
    input_path: str, output_path: str,
    encoder: str = "libx264", crf: int = 28,
    width: Optional[int] = None,
    resolution: Optional[str] = None,
    bitrate: Optional[str] = None,
    video_fps: Optional[int] = None,
    probe_data: Optional[dict] = None, **kwargs,
) -> list:
    """Build Android-compatible minimum-size MP4 command.

    Uses H.264 Baseline for maximum device compatibility, aggressive CRF,
    auto-downscale to 720p, and low-bitrate mono audio.
    """
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(input_path),
        "-c:v", encoder,
    ]
    cmd.extend(_get_hw_quality_flags(encoder, crf, bitrate=bitrate))

    if encoder == "libx264":
        cmd.extend(["-profile:v", "baseline", "-level:v", "3.1"])

    vf_parts = _build_scale_filter(width=width, resolution=resolution)
    if not vf_parts and probe_data and probe_data.get("height", 0) > 720:
        vf_parts = ["scale=-2:720"]
    if video_fps:
        vf_parts.append(f"fps={video_fps}")
    if vf_parts:
        cmd.extend(["-vf", ",".join(vf_parts)])
    elif video_fps:
        cmd.extend(["-r", str(video_fps)])

    cmd.extend([
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k", "-ac", "1",
        "-movflags", "+faststart",
        str(output_path),
    ])
    return [(cmd, "Encoding min-size MP4", None)]


def build_audio_command(
    input_path: str, output_path: str,
    audio_format: str = "mp3", **kwargs,
) -> list:
    """Build audio extraction command."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(input_path),
        "-vn",
    ]
    if audio_format == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "128k", "-q:a", "2"])
    else:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    cmd.append(str(output_path))
    return [(cmd, "Extracting audio", None)]


# ============================================================================
# Section 4: Transcoding Engine
# ============================================================================


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class TranscodeJob:
    input_path: str
    output_path: str
    preset: str
    options: dict = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    error_msg: str = ""
    progress_pct: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0


_PROGRESS_RE = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")


def parse_progress(line: str, total_duration: float) -> Optional[float]:
    """Parse FFmpeg stderr line for progress. Returns 0-100 or None."""
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    current = h * 3600 + mi * 60 + s + cs / 100.0
    if total_duration <= 0:
        return -1.0
    pct = min(100.0, max(0.0, (current / total_duration) * 100.0))
    return pct


def run_single_command(
    cmd: list,
    total_duration: float,
    progress_cb: Optional[Callable] = None,
    log_cb: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
) -> tuple:
    """Run a single FFmpeg command. Returns (success, error_message)."""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
            bufsize=1,
        )
    except Exception as e:
        return False, str(e)

    last_lines = []
    try:
        for line in proc.stderr:
            line = line.rstrip()
            if log_cb:
                log_cb(line)
            last_lines.append(line)
            if len(last_lines) > 20:
                last_lines.pop(0)

            pct = parse_progress(line, total_duration)
            if pct is not None and progress_cb:
                progress_cb(pct)

            if cancel_event and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return False, "Cancelled by user"
    except Exception as e:
        proc.kill()
        return False, str(e)

    proc.wait()
    if proc.returncode != 0:
        error_context = "\n".join(last_lines[-5:])
        return False, f"FFmpeg exited with code {proc.returncode}\n{error_context}"
    return True, ""


def run_transcode(
    job: TranscodeJob,
    progress_cb: Optional[Callable] = None,
    log_cb: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
    dry_run: bool = False,
) -> bool:
    """Execute a full transcode job (may involve multiple passes)."""
    job.status = JobStatus.RUNNING
    job.start_time = time.time()

    probe_data = probe_video(job.input_path)
    total_duration = probe_data.get("duration", 0)

    available = detect_hw_encoders()
    encoder_override = job.options.get("encoder")
    crf_val = job.options.get("crf")
    width_val = job.options.get("width")
    resolution_val = job.options.get("resolution")
    bitrate_val = job.options.get("bitrate")
    video_fps_val = job.options.get("video_fps")

    if job.preset == "gif":
        fps = job.options.get("fps", 10)
        w = width_val or 480
        commands = build_gif_commands(
            job.input_path, job.output_path, fps=fps, width=w,
        )
    elif job.preset == "android":
        enc = select_encoder(H264_CHAIN, available, encoder_override)
        crf = crf_val if crf_val is not None else 23
        commands = build_android_command(
            job.input_path, job.output_path,
            encoder=enc, crf=crf, width=width_val,
            resolution=resolution_val, bitrate=bitrate_val,
            video_fps=video_fps_val,
        )
        if log_cb:
            log_cb(f"  Using encoder: {enc}")
    elif job.preset == "minsize":
        enc = select_encoder(H264_CHAIN, available, encoder_override)
        crf = crf_val if crf_val is not None else 28
        commands = build_minsize_command(
            job.input_path, job.output_path,
            encoder=enc, crf=crf, width=width_val,
            resolution=resolution_val, bitrate=bitrate_val,
            video_fps=video_fps_val, probe_data=probe_data,
        )
        if log_cb:
            log_cb(f"  Using encoder: {enc}")
    elif job.preset == "audio":
        audio_fmt = job.options.get("audio_format", "mp3")
        commands = build_audio_command(
            job.input_path, job.output_path,
            audio_format=audio_fmt,
        )
    else:
        job.status = JobStatus.FAILED
        job.error_msg = f"Unknown preset: {job.preset}"
        return False

    if dry_run:
        for cmd, desc, _ in commands:
            if log_cb:
                log_cb(f"[DRY-RUN] {desc}")
                log_cb(f"  {' '.join(cmd)}")
        job.status = JobStatus.DONE
        job.end_time = time.time()
        return True

    os.makedirs(os.path.dirname(job.output_path) or ".", exist_ok=True)

    palette_to_clean = None
    try:
        for i, (cmd, desc, palette_path) in enumerate(commands):
            if palette_path:
                palette_to_clean = palette_path

            if log_cb:
                log_cb(f"  Pass {i + 1}/{len(commands)}: {desc}")

            ok, err = run_single_command(
                cmd, total_duration, progress_cb, log_cb, cancel_event,
            )
            if not ok:
                job.status = (
                    JobStatus.CANCELLED if "Cancelled" in err
                    else JobStatus.FAILED
                )
                job.error_msg = err
                _cleanup_partial(job.output_path)
                return False

        if os.path.isfile(job.output_path) and os.path.getsize(job.output_path) > 0:
            job.status = JobStatus.DONE
            job.end_time = time.time()
            if progress_cb:
                progress_cb(100.0)
            return True
        else:
            job.status = JobStatus.FAILED
            job.error_msg = "Output file missing or empty"
            return False
    finally:
        if palette_to_clean and os.path.isfile(palette_to_clean):
            try:
                os.remove(palette_to_clean)
            except OSError:
                pass


def _cleanup_partial(path: str):
    """Remove partial output file if it exists."""
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


# ============================================================================
# Section 5: Batch Job Manager
# ============================================================================


def collect_input_files(paths: list, recursive: bool = False) -> list:
    """Collect video files from given paths (files or directories).

    Returns a list of (file_path, relative_subdir) tuples.
    relative_subdir is the subdirectory path relative to the input root,
    used to mirror directory structure in the output.
    For directly specified files, relative_subdir is Path('.').
    """
    result = []
    seen = set()
    for p in paths:
        p = Path(p)
        if p.is_file():
            if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                rp = str(p.resolve())
                if rp not in seen:
                    seen.add(rp)
                    result.append((p, Path(".")))
        elif p.is_dir():
            glob_fn = p.rglob if recursive else p.glob
            for f in sorted(glob_fn("*")):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                    rf = str(f.resolve())
                    if rf not in seen:
                        seen.add(rf)
                        try:
                            rel = f.parent.relative_to(p)
                        except ValueError:
                            rel = Path(".")
                        result.append((f, rel))
    return result


def build_output_path(
    input_path: Path, output_dir: Path, preset: str,
    audio_format: str = "mp3", relative_subdir: Optional[Path] = None,
) -> Path:
    """Build output file path with appropriate extension.

    If relative_subdir is provided, mirrors the input directory structure
    under output_dir.
    """
    ext_map = {
        "gif": ".gif",
        "android": ".mp4",
        "minsize": ".mp4",
        "audio": f".{audio_format}" if audio_format == "mp3" else ".m4a",
    }
    ext = ext_map.get(preset, ".mp4")
    stem = input_path.stem
    base_name = f"{stem}_{preset}{ext}"

    target_dir = output_dir
    if relative_subdir and str(relative_subdir) != ".":
        target_dir = output_dir / relative_subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    out = target_dir / base_name

    counter = 1
    while out.exists():
        out = target_dir / f"{stem}_{preset}_{counter}{ext}"
        counter += 1
    return out


@dataclass
class BatchSummary:
    total: int = 0
    done: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: int = 0
    elapsed: float = 0.0
    failed_files: list = field(default_factory=list)


def run_batch(
    jobs: list,
    progress_cb: Optional[Callable] = None,
    log_cb: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
    dry_run: bool = False,
) -> BatchSummary:
    """Run all transcode jobs sequentially."""
    summary = BatchSummary(total=len(jobs))
    batch_start = time.time()

    for i, job in enumerate(jobs):
        if cancel_event and cancel_event.is_set():
            job.status = JobStatus.SKIPPED
            summary.skipped += 1
            continue

        if log_cb:
            log_cb(
                f"\n[{i + 1}/{len(jobs)}] {os.path.basename(job.input_path)}"
                f" -> {job.preset}"
            )

        def _file_progress(pct, idx=i):
            if progress_cb:
                overall = (idx + (max(0, pct) / 100.0)) / len(jobs) * 100.0
                progress_cb(pct, overall, idx)

        ok = run_transcode(
            job, progress_cb=_file_progress, log_cb=log_cb,
            cancel_event=cancel_event, dry_run=dry_run,
        )

        if job.status == JobStatus.DONE:
            summary.done += 1
            if log_cb and not dry_run:
                elapsed = job.end_time - job.start_time
                out_size = (
                    os.path.getsize(job.output_path)
                    if os.path.isfile(job.output_path) else 0
                )
                log_cb(
                    f"  [DONE] {os.path.basename(job.output_path)}"
                    f" ({_format_size(out_size)}, {elapsed:.1f}s)"
                )
        elif job.status == JobStatus.FAILED:
            summary.failed += 1
            summary.failed_files.append(job.input_path)
            if log_cb:
                log_cb(f"  [FAIL] {job.error_msg}")
        elif job.status == JobStatus.CANCELLED:
            summary.cancelled += 1
        else:
            summary.skipped += 1

    summary.elapsed = time.time() - batch_start
    return summary


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"


# ============================================================================
# Section 5.5: Ad Detection & Removal (Deadvert)
# ============================================================================


@dataclass
class AdSegment:
    start: float
    end: float
    confidence: float = 1.0
    source_videos: list = field(default_factory=list)


@dataclass
class DeadvertResult:
    video_path: str
    ad_segments: list = field(default_factory=list)
    clean_segments: list = field(default_factory=list)
    trimmed_output: str = ""


@dataclass
class DeadvertSummary:
    total_videos: int = 0
    videos_with_ads: int = 0
    total_ads_found: int = 0
    total_time_removed: float = 0.0
    results: list = field(default_factory=list)


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def check_deadvert_deps(method: str) -> tuple:
    """Check if dependencies for the chosen detection method are available.

    Returns (ok: bool, error_msg: str).
    """
    if method == "audio":
        if shutil.which("fpcalc"):
            return (True, "")
        return (False, _t("deadvert_dep_fpcalc"))
    else:  # video
        try:
            import PIL  # noqa: F401
            import imagehash  # noqa: F401
            return (True, "")
        except ImportError:
            return (False, _t("deadvert_dep_pillow"))


# -- Audio fingerprint backend -----------------------------------------------

def extract_audio_fingerprints(video_path: str, duration: float) -> list:
    """Extract raw chromaprint fingerprints via fpcalc.

    Returns a list of uint32 integers, each representing ~0.12s of audio.
    """
    length = max(int(duration) + 1, 10)
    try:
        result = subprocess.run(
            ["fpcalc", "-raw", "-length", str(length), "-json", video_path],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        log.warning("fpcalc timed out for %s", video_path)
        return []
    except FileNotFoundError:
        return []

    if result.returncode != 0:
        log.warning("fpcalc failed for %s: %s", video_path, result.stderr.strip())
        return []

    try:
        data = json.loads(result.stdout)
        return data.get("fingerprint", [])
    except (json.JSONDecodeError, KeyError):
        return []


def _popcount_xor(a: int, b: int) -> int:
    """Count differing bits between two uint32 values."""
    return bin((a ^ b) & 0xFFFFFFFF).count("1")


def find_matching_segments_audio(
    fp_a: list, fp_b: list,
    window_sec: float = 10.0,
    min_match_sec: float = 5.0,
    threshold_bits: int = 10,
) -> list:
    """Find matching segments between two audio fingerprint arrays.

    Uses a sliding-window approach with hamming distance on uint32 XOR.
    Returns list of (start_a, end_a, start_b, end_b, confidence) tuples
    with times in seconds.
    """
    RATE = 0.12  # seconds per fingerprint sample
    win_samples = max(int(window_sec / RATE), 10)
    stride = max(win_samples // 2, 1)
    min_match_samples = int(min_match_sec / RATE)

    if len(fp_a) < win_samples or len(fp_b) < win_samples:
        return []

    matches = []  # (pos_a, pos_b)

    for ia in range(0, len(fp_a) - win_samples + 1, stride):
        win_a = fp_a[ia:ia + win_samples]
        best_dist = float("inf")
        best_ib = -1

        for ib in range(0, len(fp_b) - win_samples + 1, stride):
            win_b = fp_b[ib:ib + win_samples]
            total_dist = 0
            for va, vb in zip(win_a, win_b):
                total_dist += _popcount_xor(va, vb)
            avg_dist = total_dist / win_samples
            if avg_dist < best_dist:
                best_dist = avg_dist
                best_ib = ib

        if best_dist <= threshold_bits:
            confidence = max(0.0, 1.0 - best_dist / 32.0)
            matches.append((ia, best_ib, confidence))

    if not matches:
        return []

    # Merge consecutive matches into segments
    segments = []
    seg_start_a, seg_start_b = matches[0][0], matches[0][1]
    seg_end_a = matches[0][0] + win_samples
    seg_end_b = matches[0][1] + win_samples
    seg_conf = [matches[0][2]]

    for ma, mb, conf in matches[1:]:
        # If this match is close enough to the current segment, extend it
        if ma <= seg_end_a + stride and mb <= seg_end_b + stride:
            seg_end_a = max(seg_end_a, ma + win_samples)
            seg_end_b = max(seg_end_b, mb + win_samples)
            seg_conf.append(conf)
        else:
            if seg_end_a - seg_start_a >= min_match_samples:
                segments.append((
                    seg_start_a * RATE, seg_end_a * RATE,
                    seg_start_b * RATE, seg_end_b * RATE,
                    sum(seg_conf) / len(seg_conf),
                ))
            seg_start_a, seg_start_b = ma, mb
            seg_end_a = ma + win_samples
            seg_end_b = mb + win_samples
            seg_conf = [conf]

    if seg_end_a - seg_start_a >= min_match_samples:
        segments.append((
            seg_start_a * RATE, seg_end_a * RATE,
            seg_start_b * RATE, seg_end_b * RATE,
            sum(seg_conf) / len(seg_conf),
        ))

    return segments


# -- Video frame hash backend ------------------------------------------------

def extract_frame_hashes(video_path: str, interval: float = 1.0) -> list:
    """Extract perceptual hashes for video frames at regular intervals.

    Returns list of (timestamp_sec, hash_hex) tuples.
    """
    try:
        from PIL import Image
        import imagehash
    except ImportError:
        return []

    tmpdir = tempfile.mkdtemp(prefix="lapian_frames_")
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", video_path,
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",
            os.path.join(tmpdir, "frame_%06d.jpg"),
        ]
        subprocess.run(cmd, capture_output=True, timeout=300)

        hashes = []
        frame_files = sorted(
            f for f in os.listdir(tmpdir) if f.startswith("frame_")
        )
        for idx, fname in enumerate(frame_files):
            ts = idx * interval
            fpath = os.path.join(tmpdir, fname)
            try:
                img = Image.open(fpath)
                h = str(imagehash.phash(img))
                hashes.append((ts, h))
            except Exception:
                continue
        return hashes
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _hamming_hex(h1: str, h2: str) -> int:
    """Compute hamming distance between two hex-encoded hashes."""
    try:
        v1 = int(h1, 16)
        v2 = int(h2, 16)
        return bin(v1 ^ v2).count("1")
    except ValueError:
        return 64


def find_matching_segments_video(
    hashes_a: list, hashes_b: list,
    interval: float = 1.0,
    max_hamming: int = 12,
    min_run: int = 5,
) -> list:
    """Find matching segments between two frame hash sequences.

    Returns list of (start_a, end_a, start_b, end_b, confidence) tuples
    with times in seconds.
    """
    if not hashes_a or not hashes_b:
        return []

    # Build index: for each hash in B, store positions
    # Use approximate matching: group by first 8 hex chars
    b_index = {}
    for ib, (ts_b, hb) in enumerate(hashes_b):
        prefix = hb[:4]
        b_index.setdefault(prefix, []).append(ib)

    # For each frame in A, find candidate matches in B
    pair_matches = {}  # (ia, ib) -> hamming distance
    for ia, (ts_a, ha) in enumerate(hashes_a):
        prefix = ha[:4]
        candidates = set()
        for p, ibs in b_index.items():
            # Check prefixes with small distance
            if _hamming_hex(prefix, p) <= 4:
                candidates.update(ibs)
        for ib in candidates:
            dist = _hamming_hex(ha, hashes_b[ib][1])
            if dist <= max_hamming:
                pair_matches[(ia, ib)] = dist

    if not pair_matches:
        return []

    # Find diagonal runs: consecutive (ia, ib), (ia+1, ib+1), ...
    segments = []
    visited = set()

    for (ia, ib) in sorted(pair_matches.keys()):
        if (ia, ib) in visited:
            continue
        # Extend run along the diagonal
        run_len = 1
        visited.add((ia, ib))
        while (ia + run_len, ib + run_len) in pair_matches:
            visited.add((ia + run_len, ib + run_len))
            run_len += 1

        if run_len >= min_run:
            total_dist = sum(
                pair_matches[(ia + k, ib + k)] for k in range(run_len)
            )
            avg_dist = total_dist / run_len
            confidence = max(0.0, 1.0 - avg_dist / 64.0)
            segments.append((
                hashes_a[ia][0],
                hashes_a[ia + run_len - 1][0] + interval,
                hashes_b[ib][0],
                hashes_b[ib + run_len - 1][0] + interval,
                confidence,
            ))

    return segments


# -- Segment aggregation & trimming ------------------------------------------

def aggregate_ad_segments(
    all_matches: dict,
    video_paths: list,
    durations: dict,
    threshold: int = 2,
    min_duration: float = 5.0,
) -> dict:
    """Aggregate matched segments across video pairs to identify ads.

    all_matches: dict keyed by (i, j) index pairs, values are match lists.
    Returns dict mapping video_path -> list[AdSegment].
    """
    # Collect per-video segments with source info
    raw_segments = {p: [] for p in video_paths}

    for (i, j), matches in all_matches.items():
        path_i = video_paths[i]
        path_j = video_paths[j]
        for (start_a, end_a, start_b, end_b, conf) in matches:
            raw_segments[path_i].append(
                AdSegment(start=start_a, end=end_a, confidence=conf,
                          source_videos=[path_j])
            )
            raw_segments[path_j].append(
                AdSegment(start=start_b, end=end_b, confidence=conf,
                          source_videos=[path_i])
            )

    result = {}
    for path in video_paths:
        segs = raw_segments[path]
        if not segs:
            result[path] = []
            continue

        # Sort by start time
        segs.sort(key=lambda s: s.start)

        # Merge overlapping segments
        merged = [segs[0]]
        for seg in segs[1:]:
            prev = merged[-1]
            if seg.start <= prev.end + 1.0:
                # Merge: extend end, combine sources
                prev.end = max(prev.end, seg.end)
                prev.confidence = max(prev.confidence, seg.confidence)
                for v in seg.source_videos:
                    if v not in prev.source_videos:
                        prev.source_videos.append(v)
            else:
                merged.append(seg)

        # Filter: must appear in at least (threshold - 1) other videos
        # and meet minimum duration
        filtered = []
        for seg in merged:
            if len(seg.source_videos) >= (threshold - 1):
                if (seg.end - seg.start) >= min_duration:
                    filtered.append(seg)

        result[path] = filtered

    return result


def compute_clean_segments(
    duration: float,
    ad_segments: list,
    margin: float = 0.5,
) -> list:
    """Invert ad segments to get the 'keep' regions.

    Returns list of (start, end) tuples representing clean video portions.
    """
    if not ad_segments:
        return [(0.0, duration)]

    # Sort ads by start time
    ads = sorted(ad_segments, key=lambda s: s.start)

    clean = []
    pos = 0.0

    for ad in ads:
        ad_start = max(0.0, ad.start - margin)
        ad_end = min(duration, ad.end + margin)

        if ad_start > pos + 0.1:
            clean.append((pos, ad_start))
        pos = ad_end

    if pos < duration - 0.1:
        clean.append((pos, duration))

    return clean


def trim_video(
    input_path: str,
    clean_segments: list,
    output_path: str,
    cancel_event: Optional[threading.Event] = None,
    log_cb: Optional[Callable] = None,
) -> tuple:
    """Trim video to keep only clean segments using ffmpeg stream-copy.

    Returns (success: bool, error_msg: str).
    """
    if not clean_segments:
        return (False, "No clean segments to keep")

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    if len(clean_segments) == 1:
        start, end = clean_segments[0]
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(start), "-to", str(end),
            "-i", input_path,
            "-c", "copy",
            "-map", "0",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                return (False, result.stderr.strip()[-200:])
            return (True, "")
        except subprocess.TimeoutExpired:
            return (False, "ffmpeg timed out")
    else:
        # Multiple segments: extract each, then concat
        tmpdir = tempfile.mkdtemp(prefix="lapian_trim_")
        try:
            seg_files = []
            for idx, (start, end) in enumerate(clean_segments):
                if cancel_event and cancel_event.is_set():
                    return (False, "Cancelled")
                seg_path = os.path.join(tmpdir, f"seg_{idx:04d}{Path(input_path).suffix}")
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(start), "-to", str(end),
                    "-i", input_path,
                    "-c", "copy",
                    "-map", "0",
                    seg_path,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300,
                )
                if result.returncode != 0:
                    return (False, f"Segment {idx} extraction failed: {result.stderr.strip()[-200:]}")
                seg_files.append(seg_path)

            # Write concat list
            concat_list = os.path.join(tmpdir, "concat.txt")
            with open(concat_list, "w", encoding="utf-8") as f:
                for sf in seg_files:
                    f.write(f"file {sf!r}\n")

            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                "-movflags", "+faststart",
                output_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                return (False, f"Concat failed: {result.stderr.strip()[-200:]}")
            return (True, "")
        except subprocess.TimeoutExpired:
            return (False, "ffmpeg timed out during concat")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def run_deadvert(
    video_paths: list,
    method: str = "audio",
    threshold: int = 2,
    min_duration: float = 5.0,
    interval: float = 1.0,
    output_dir: str = "./transcoded",
    confirm_cb: Optional[Callable] = None,
    progress_cb: Optional[Callable] = None,
    log_cb: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
) -> DeadvertSummary:
    """Run the full ad detection and removal pipeline.

    confirm_cb: Optional callback(DeadvertSummary) -> bool.
                If provided, called after detection to confirm trimming.
    progress_cb: Optional callback(file_pct, overall_pct, idx).
    log_cb: Optional callback(msg: str).
    Returns DeadvertSummary.
    """
    summary = DeadvertSummary(total_videos=len(video_paths))

    def _log(msg):
        if log_cb:
            log_cb(msg)

    # 1. Validate
    if len(video_paths) < 2:
        _log(_t("deadvert_need_multiple"))
        return summary

    # 2. Check dependencies
    ok, err = check_deadvert_deps(method)
    if not ok:
        _log(f"ERROR: {err}")
        return summary

    _log(_t("deadvert_detecting"))

    # 3. Probe all videos
    durations = {}
    has_audio = {}
    for vp in video_paths:
        info = probe_video(vp)
        durations[vp] = info.get("duration", 0)
        has_audio[vp] = info.get("has_audio", True)

    # 4. Extract fingerprints / hashes
    fingerprints = {}
    valid_paths = []

    for idx, vp in enumerate(video_paths):
        if cancel_event and cancel_event.is_set():
            return summary

        _log(_t("deadvert_extracting", current=idx + 1, total=len(video_paths)))

        if method == "audio":
            if not has_audio.get(vp, True):
                _log(_t("deadvert_skipped_no_audio", name=os.path.basename(vp)))
                continue
            fp = extract_audio_fingerprints(vp, durations.get(vp, 60))
            if fp:
                fingerprints[vp] = fp
                valid_paths.append(vp)
        else:
            hashes = extract_frame_hashes(vp, interval=interval)
            if hashes:
                fingerprints[vp] = hashes
                valid_paths.append(vp)

    if method == "audio" and not valid_paths:
        _log(_t("deadvert_suggest_video"))
        return summary

    if len(valid_paths) < 2:
        _log(_t("deadvert_need_multiple"))
        return summary

    # 5. Cross-correlate all pairs
    all_matches = {}
    n = len(valid_paths)
    total_pairs = n * (n - 1) // 2
    pair_idx = 0

    for i in range(n):
        for j in range(i + 1, n):
            if cancel_event and cancel_event.is_set():
                return summary

            pair_idx += 1
            _log(_t("deadvert_correlating", current=pair_idx, total=total_pairs))

            vi_idx = video_paths.index(valid_paths[i])
            vj_idx = video_paths.index(valid_paths[j])

            if method == "audio":
                segs = find_matching_segments_audio(
                    fingerprints[valid_paths[i]],
                    fingerprints[valid_paths[j]],
                    min_match_sec=min_duration,
                )
            else:
                segs = find_matching_segments_video(
                    fingerprints[valid_paths[i]],
                    fingerprints[valid_paths[j]],
                    interval=interval,
                    min_run=max(int(min_duration / interval), 3),
                )

            if segs:
                all_matches[(vi_idx, vj_idx)] = segs

    # 6. Aggregate
    ad_map = aggregate_ad_segments(
        all_matches, video_paths, durations,
        threshold=threshold, min_duration=min_duration,
    )

    # Build results
    for vp in video_paths:
        ads = ad_map.get(vp, [])
        dur = durations.get(vp, 0)
        clean = compute_clean_segments(dur, ads)
        result = DeadvertResult(
            video_path=vp,
            ad_segments=ads,
            clean_segments=clean,
        )
        summary.results.append(result)
        if ads:
            summary.videos_with_ads += 1
            summary.total_ads_found += len(ads)
            summary.total_time_removed += sum(a.end - a.start for a in ads)

    if summary.total_ads_found == 0:
        _log(_t("deadvert_no_ads"))
        return summary

    _log(_t("deadvert_found",
            count=summary.total_ads_found,
            videos=summary.videos_with_ads))

    # 7. Confirm if callback provided
    if confirm_cb is not None:
        if not confirm_cb(summary):
            return summary

    # 8. Trim
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, result in enumerate(summary.results):
        if cancel_event and cancel_event.is_set():
            break

        _log(_t("deadvert_trimming", current=idx + 1, total=len(summary.results)))
        vp = result.video_path
        basename = Path(vp).stem
        ext = Path(vp).suffix
        out_path = str(out_dir / f"{basename}_deadvert{ext}")

        if not result.ad_segments:
            # No ads: copy original
            _log(_t("deadvert_no_change", name=os.path.basename(vp)))
            shutil.copy2(vp, out_path)
            result.trimmed_output = out_path
            continue

        # Check if entire video is ad
        total_clean = sum(e - s for s, e in result.clean_segments)
        if total_clean < 1.0:
            _log(_t("deadvert_video_all_ad", name=os.path.basename(vp)))
            continue

        ok, err = trim_video(
            vp, result.clean_segments, out_path,
            cancel_event=cancel_event, log_cb=log_cb,
        )
        if ok:
            result.trimmed_output = out_path
            _log(f"  [DONE] {os.path.basename(out_path)}")
        else:
            _log(f"  [FAIL] {os.path.basename(vp)}: {err}")

    _log(_t("deadvert_total_removed", time=summary.total_time_removed))
    return summary


# ============================================================================
# Section 6: CLI Interface
# ============================================================================


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lapian",
        description="LaPian (拉片) — Batch Video Transcoder with hardware acceleration support.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s -p android video.mp4\n"
            "  %(prog)s -p gif -o ./gifs --fps 15 --width 320 *.mp4\n"
            "  %(prog)s -p minsize -r /path/to/videos/\n"
            "  %(prog)s -p audio --audio-format aac video.mkv\n"
            "  %(prog)s --deadvert ep01.mp4 ep02.mp4 ep03.mp4\n"
            "  %(prog)s --deadvert -p android --confirm ep*.mp4\n"
            "  %(prog)s --gui\n"
        ),
    )
    parser.add_argument(
        "input", nargs="*", default=[],
        help="Input video files or directories",
    )
    parser.add_argument(
        "-p", "--preset", choices=PRESET_NAMES,
        help="Transcoding preset: gif, android, minsize, audio",
    )
    parser.add_argument(
        "-o", "--output", default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true", default=True,
        help="Recursively search directories for videos (default: on)",
    )
    parser.add_argument(
        "--no-recursive", action="store_true",
        help="Disable recursive directory search",
    )
    parser.add_argument(
        "--encoder", default=None,
        help="Force a specific encoder (e.g., h264_nvenc, libx264)",
    )
    parser.add_argument("--crf", type=int, default=None, help="Override CRF value")
    parser.add_argument(
        "--fps", type=int, default=10,
        help="GIF framerate (default: 10)",
    )
    parser.add_argument(
        "--width", type=int, default=None,
        help="Max output width in pixels",
    )
    parser.add_argument(
        "--audio-format", choices=["mp3", "aac"], default="mp3",
        help="Audio format for audio preset (default: mp3)",
    )
    parser.add_argument(
        "--resolution", default=None,
        choices=RESOLUTION_CHOICES,
        help="Output resolution (default: original)",
    )
    parser.add_argument(
        "--bitrate", default=None,
        help="Video bitrate, e.g. 2M, 500k (default: CRF-based quality)",
    )
    parser.add_argument(
        "--video-fps", type=int, default=None,
        choices=FPS_CHOICES,
        help="Output video framerate (default: original)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print FFmpeg commands without executing",
    )
    parser.add_argument(
        "--gui", action="store_true",
        help="Launch GUI mode",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Verbose FFmpeg output",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    # -- Deadvert arguments --
    deadvert_group = parser.add_argument_group("deadvert (ad removal)")
    deadvert_group.add_argument(
        "--deadvert", action="store_true",
        help="Enable automatic ad detection and removal across multiple videos",
    )
    deadvert_group.add_argument(
        "--deadvert-method", choices=["audio", "video"], default="audio",
        help="Detection method: audio fingerprint (needs fpcalc) or video frame hash (needs Pillow+imagehash). Default: audio",
    )
    deadvert_group.add_argument(
        "--deadvert-threshold", type=int, default=2,
        help="Minimum number of videos a segment must appear in to be considered an ad (default: 2)",
    )
    deadvert_group.add_argument(
        "--deadvert-min-duration", type=float, default=5.0,
        help="Minimum ad segment duration in seconds (default: 5.0)",
    )
    deadvert_group.add_argument(
        "--deadvert-interval", type=float, default=1.0,
        help="Frame extraction interval in seconds for video method (default: 1.0)",
    )
    deadvert_group.add_argument(
        "--confirm", action="store_true",
        help="Preview detected ad segments before trimming",
    )
    deadvert_group.add_argument(
        "--detect-only", action="store_true",
        help="Only detect and report ad segments, do not trim",
    )
    return parser


def run_cli(args) -> int:
    """Run the CLI transcoder. Returns exit code."""
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(message)s", stream=sys.stderr,
    )

    try:
        check_ffmpeg()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    files = collect_input_files(args.input, not args.no_recursive)
    if not files:
        print(_t("no_video_cli"), file=sys.stderr)
        return 1
    print(_t("found_cli", count=len(files)))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    cancel_event = threading.Event()

    def cli_log(msg):
        if args.verbose or not msg.startswith("frame="):
            print(msg, file=sys.stderr)

    # -- Deadvert preprocessing --
    if getattr(args, "deadvert", False):
        video_paths = [str(f) for f, _ in files]

        def cli_confirm_deadvert(dv_summary):
            print(f"\n{_t('deadvert_report_header')}")
            print("-" * 50)
            for r in dv_summary.results:
                if r.ad_segments:
                    print(_t("deadvert_report_video",
                             name=os.path.basename(r.video_path)))
                    for n, ad in enumerate(r.ad_segments, 1):
                        print(_t("deadvert_report_seg",
                                 n=n,
                                 start=format_timestamp(ad.start),
                                 end=format_timestamp(ad.end),
                                 duration=ad.end - ad.start,
                                 count=len(ad.source_videos) + 1))
            print("-" * 50)
            print(_t("deadvert_total_removed",
                      time=dv_summary.total_time_removed))
            print()
            resp = input(_t("deadvert_confirm_prompt")).strip().lower()
            return resp in ("", "y", "yes")

        confirm_cb = cli_confirm_deadvert if args.confirm else None

        dv_summary = run_deadvert(
            video_paths,
            method=args.deadvert_method,
            threshold=args.deadvert_threshold,
            min_duration=args.deadvert_min_duration,
            interval=args.deadvert_interval,
            output_dir=str(output_dir),
            confirm_cb=confirm_cb,
            log_cb=cli_log,
            cancel_event=cancel_event,
        )

        # --detect-only: just print report and exit
        if getattr(args, "detect_only", False):
            if dv_summary.total_ads_found == 0:
                print(_t("deadvert_no_ads"))
            else:
                print(f"\n{_t('deadvert_report_header')}")
                print("-" * 50)
                for r in dv_summary.results:
                    if r.ad_segments:
                        print(_t("deadvert_report_video",
                                 name=os.path.basename(r.video_path)))
                        for n, ad in enumerate(r.ad_segments, 1):
                            print(_t("deadvert_report_seg",
                                     n=n,
                                     start=format_timestamp(ad.start),
                                     end=format_timestamp(ad.end),
                                     duration=ad.end - ad.start,
                                     count=len(ad.source_videos) + 1))
                print("-" * 50)
                print(_t("deadvert_total_removed",
                          time=dv_summary.total_time_removed))
            return 0

        # If no preset, deadvert output is the final output
        if not args.preset:
            print(f"\n{'='*50}")
            print(_t("deadvert_found",
                      count=dv_summary.total_ads_found,
                      videos=dv_summary.videos_with_ads))
            print(_t("deadvert_total_removed",
                      time=dv_summary.total_time_removed))
            print(f"{'='*50}")
            return 0

        # If preset provided, use trimmed files as input for transcoding
        trimmed_files = []
        for r in dv_summary.results:
            if r.trimmed_output and os.path.isfile(r.trimmed_output):
                trimmed_files.append((Path(r.trimmed_output), Path(".")))
            else:
                trimmed_files.append(
                    (Path(r.video_path), Path(".")))
        files = trimmed_files

    # -- Normal transcoding flow --
    if not args.preset:
        print("ERROR: --preset is required for transcoding.", file=sys.stderr)
        return 1

    encoders = detect_hw_encoders()
    hw_available = [k for k, v in encoders.items() if v and k not in (
        "libx264", "libx265", "libmp3lame", "aac", "libvpx")]
    if hw_available:
        print(_t("hw_detect_cli", encoders=", ".join(hw_available)))
    else:
        print(_t("no_hw_cli"))

    jobs = []
    for f, rel_subdir in files:
        out = build_output_path(
            f, output_dir, args.preset, args.audio_format,
            relative_subdir=rel_subdir,
        )
        job = TranscodeJob(
            input_path=str(f),
            output_path=str(out),
            preset=args.preset,
            options={
                "encoder": args.encoder,
                "crf": args.crf,
                "fps": args.fps,
                "width": args.width,
                "audio_format": args.audio_format,
                "resolution": args.resolution,
                "bitrate": args.bitrate,
                "video_fps": args.video_fps,
            },
        )
        jobs.append(job)

    def cli_progress(file_pct, overall_pct, idx):
        bar_len = 30
        filled = int(bar_len * max(0, file_pct) / 100)
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stderr.write(
            f"\r  [{bar}] {file_pct:5.1f}%  (overall: {overall_pct:.1f}%)"
        )
        sys.stderr.flush()

    summary = run_batch(
        jobs,
        progress_cb=cli_progress,
        log_cb=cli_log,
        cancel_event=cancel_event,
        dry_run=args.dry_run,
    )

    sys.stderr.write("\n")
    print(f"\n{'='*50}")
    print(_t("batch_summary", done=summary.done, failed=summary.failed,
             skipped=summary.skipped, elapsed=summary.elapsed))
    if summary.failed_files:
        print(_t("failed_files_cli"))
        for fp in summary.failed_files:
            print(f"  - {fp}")
    print(f"{'='*50}")

    return 1 if summary.failed > 0 else 0


# ============================================================================
# Section 7: GUI Interface (tkinter)
# ============================================================================


def launch_gui():
    """Launch the tkinter GUI."""
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, scrolledtext, messagebox
    except ImportError:
        print(
            "ERROR: tkinter is not available.\n"
            "Install it with:\n"
            "  Ubuntu/Debian: sudo apt install python3-tk\n"
            "  Fedora: sudo dnf install python3-tkinter\n"
            "  macOS: brew install python-tk",
            file=sys.stderr,
        )
        sys.exit(1)

    class TranscoderGUI:
        def __init__(self, root: tk.Tk):
            self.root = root
            self.root.title("LaPian (拉片)")
            self.root.minsize(950, 680)
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(2, weight=1)

            self.cancel_event = threading.Event()
            self.worker_thread = None
            self.file_paths = []

            # Pick a monospace font that supports CJK characters
            self._mono_font = self._pick_mono_font()
            # Pick a proportional font for lists that reliably renders CJK
            self._list_font = self._pick_list_font()

            self._build_ui()
            self._detect_hw_on_startup()

        @staticmethod
        def _pick_list_font():
            """Return a (family, size) tuple for the file list with CJK support."""
            import tkinter.font as tkfont
            families = set(tkfont.families())
            # Prefer proportional CJK fonts (more reliable in tkinter)
            for name in (
                "Noto Sans CJK SC",
                "WenQuanYi Micro Hei",
                "WenQuanYi Zen Hei",
                "Microsoft YaHei",
                "SimSun",
                "PingFang SC",
                "Hiragino Sans",
            ):
                if name in families:
                    return (name, 9)
            # Fall back to tkinter default (handles CJK via system config)
            return ("TkDefaultFont", 9)

        @staticmethod
        def _pick_mono_font():
            """Return a (family, size) tuple for a monospace font with CJK support."""
            import tkinter.font as tkfont
            families = set(tkfont.families())
            # Try mono CJK fonts first, then fall back to system mono
            for name in (
                "WenQuanYi Micro Hei Mono",
                "WenQuanYi Zen Hei Mono",
                "Noto Sans Mono CJK SC",
                "Source Han Mono SC",
                "Microsoft YaHei Mono",
            ):
                if name in families:
                    # Verify the font actually renders CJK by checking metrics
                    try:
                        f = tkfont.Font(family=name, size=9)
                        # If CJK char width > 0, the font actually supports it
                        if f.measure("\u4e2d") > 0:
                            return (name, 9)
                    except Exception:
                        continue
            # Fall back to system defaults
            for name in ("Consolas", "Courier New"):
                if name in families:
                    return (name, 9)
            return ("TkFixedFont", 9)

        def _build_ui(self):
            # --- Top toolbar ---
            toolbar = ttk.Frame(self.root, padding=5)
            toolbar.grid(row=0, column=0, sticky="ew")

            ttk.Button(toolbar, text=_t("add_files"), command=self._add_files).pack(
                side="left", padx=2)
            ttk.Button(toolbar, text=_t("add_directory"), command=self._add_directory).pack(
                side="left", padx=2)
            ttk.Button(toolbar, text=_t("clear_list"), command=self._clear_list).pack(
                side="left", padx=2)
            ttk.Button(toolbar, text=_t("about"), command=self._show_about).pack(
                side="right", padx=2)

            self.file_count_var = tk.StringVar(value=_t("items", count=0))
            ttk.Label(toolbar, textvariable=self.file_count_var).pack(
                side="left", padx=10)

            # --- Middle area: file list + options ---
            mid = ttk.PanedWindow(self.root, orient="horizontal")
            mid.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
            self.root.rowconfigure(1, weight=1)

            # File list
            list_frame = ttk.LabelFrame(mid, text=_t("file_queue"), padding=5)
            self.file_listbox = tk.Listbox(
                list_frame, selectmode="extended",
                font=self._list_font,
            )
            list_sb = ttk.Scrollbar(
                list_frame, orient="vertical", command=self.file_listbox.yview)
            self.file_listbox.configure(yscrollcommand=list_sb.set)
            self.file_listbox.pack(side="left", fill="both", expand=True)
            list_sb.pack(side="right", fill="y")
            mid.add(list_frame, weight=3)

            # Options panel
            opt_frame = ttk.LabelFrame(mid, text=_t("options"), padding=10)
            mid.add(opt_frame, weight=1)

            row = 0
            ttk.Label(opt_frame, text=_t("preset")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.preset_var = tk.StringVar(value="android")
            preset_cb = ttk.Combobox(
                opt_frame, textvariable=self.preset_var,
                values=list(PRESET_NAMES), state="readonly", width=15,
            )
            preset_cb.grid(row=row, column=1, sticky="ew", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("output_dir")).grid(
                row=row, column=0, sticky="w", pady=3)
            out_frame = ttk.Frame(opt_frame)
            out_frame.grid(row=row, column=1, sticky="ew", pady=3)
            self.output_dir_var = tk.StringVar(
                value=str(Path(DEFAULT_OUTPUT_DIR).resolve()))
            ttk.Entry(out_frame, textvariable=self.output_dir_var, width=20).pack(
                side="left", fill="x", expand=True)
            ttk.Button(out_frame, text="...", width=3,
                       command=self._browse_output).pack(side="right")

            row += 1
            ttk.Label(opt_frame, text=_t("hw_encoder")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.hw_label_var = tk.StringVar(value=_t("detecting"))
            ttk.Label(opt_frame, textvariable=self.hw_label_var,
                      wraplength=200).grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Separator(opt_frame, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=8)

            row += 1
            ttk.Label(opt_frame, text=_t("crf")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.crf_var = tk.StringVar(value="")
            ttk.Entry(opt_frame, textvariable=self.crf_var, width=8).grid(
                row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("resolution")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.resolution_var = tk.StringVar(value="")
            ttk.Combobox(
                opt_frame, textvariable=self.resolution_var,
                values=[""] + RESOLUTION_CHOICES,
                state="readonly", width=12,
            ).grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("bitrate")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.bitrate_var = tk.StringVar(value="")
            ttk.Entry(opt_frame, textvariable=self.bitrate_var, width=10).grid(
                row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("video_fps")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.video_fps_var = tk.StringVar(value="")
            ttk.Combobox(
                opt_frame, textvariable=self.video_fps_var,
                values=[""] + [str(f) for f in FPS_CHOICES],
                state="readonly", width=8,
            ).grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("gif_fps")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.fps_var = tk.StringVar(value="10")
            ttk.Entry(opt_frame, textvariable=self.fps_var, width=8).grid(
                row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("max_width")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.width_var = tk.StringVar(value="")
            ttk.Entry(opt_frame, textvariable=self.width_var, width=8).grid(
                row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("audio_fmt")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.audio_fmt_var = tk.StringVar(value="mp3")
            ttk.Combobox(
                opt_frame, textvariable=self.audio_fmt_var,
                values=["mp3", "aac"], state="readonly", width=8,
            ).grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            self.recursive_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(opt_frame, text=_t("recursive"),
                            variable=self.recursive_var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3)

            row += 1
            self.dryrun_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(opt_frame, text=_t("dry_run"),
                            variable=self.dryrun_var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3)

            row += 1
            self.verbose_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(opt_frame, text=_t("verbose"),
                            variable=self.verbose_var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("encoder")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.encoder_var = tk.StringVar(value="")
            ttk.Entry(opt_frame, textvariable=self.encoder_var, width=15).grid(
                row=row, column=1, sticky="w", pady=3)

            # -- Deadvert section --
            row += 1
            ttk.Separator(opt_frame, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=8)

            row += 1
            self.deadvert_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(opt_frame, text=_t("deadvert"),
                            variable=self.deadvert_var,
                            command=self._toggle_deadvert).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("deadvert_method")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.deadvert_method_var = tk.StringVar(value="audio")
            self.deadvert_method_cb = ttk.Combobox(
                opt_frame, textvariable=self.deadvert_method_var,
                values=["audio", "video"], state="disabled", width=12,
            )
            self.deadvert_method_cb.grid(row=row, column=1, sticky="w", pady=3)

            row += 1
            ttk.Label(opt_frame, text=_t("deadvert_min_dur")).grid(
                row=row, column=0, sticky="w", pady=3)
            self.deadvert_min_dur_var = tk.StringVar(value="5.0")
            self.deadvert_min_dur_entry = ttk.Entry(
                opt_frame, textvariable=self.deadvert_min_dur_var,
                width=8, state="disabled",
            )
            self.deadvert_min_dur_entry.grid(
                row=row, column=1, sticky="w", pady=3)

            opt_frame.columnconfigure(1, weight=1)

            # --- Progress area ---
            prog_frame = ttk.LabelFrame(self.root, text=_t("progress"), padding=5)
            prog_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)

            ttk.Label(prog_frame, text=_t("file")).grid(row=0, column=0, sticky="w")
            self.file_progress_var = tk.DoubleVar(value=0)
            self.file_progress_bar = ttk.Progressbar(
                prog_frame, variable=self.file_progress_var,
                maximum=100, length=400,
            )
            self.file_progress_bar.grid(row=0, column=1, sticky="ew", padx=5)
            self.file_progress_label = tk.StringVar(value="0%")
            ttk.Label(prog_frame, textvariable=self.file_progress_label, width=15).grid(
                row=0, column=2, sticky="w")

            ttk.Label(prog_frame, text=_t("overall")).grid(row=1, column=0, sticky="w")
            self.overall_progress_var = tk.DoubleVar(value=0)
            self.overall_progress_bar = ttk.Progressbar(
                prog_frame, variable=self.overall_progress_var,
                maximum=100, length=400,
            )
            self.overall_progress_bar.grid(row=1, column=1, sticky="ew", padx=5)
            self.overall_progress_label = tk.StringVar(value="0%")
            ttk.Label(prog_frame, textvariable=self.overall_progress_label, width=15).grid(
                row=1, column=2, sticky="w")
            prog_frame.columnconfigure(1, weight=1)

            # --- Buttons ---
            btn_frame = ttk.Frame(self.root, padding=5)
            btn_frame.grid(row=3, column=0, sticky="ew", padx=5)

            self.start_btn = ttk.Button(
                btn_frame, text=_t("start"), command=self._start)
            self.start_btn.pack(side="left", padx=5)
            self.cancel_btn = ttk.Button(
                btn_frame, text=_t("cancel"), command=self._cancel, state="disabled")
            self.cancel_btn.pack(side="left", padx=5)

            # --- Log area ---
            log_frame = ttk.LabelFrame(self.root, text=_t("log"), padding=5)
            log_frame.grid(row=4, column=0, sticky="nsew", padx=5, pady=5)
            self.root.rowconfigure(4, weight=2)

            self.log_area = scrolledtext.ScrolledText(
                log_frame, height=10, state="disabled",
                font=self._mono_font, wrap="word",
            )
            self.log_area.pack(fill="both", expand=True)
            self.log_area.tag_config("INFO", foreground="black")
            self.log_area.tag_config("DONE", foreground="green")
            self.log_area.tag_config("WARN", foreground="orange")
            self.log_area.tag_config("ERROR", foreground="red")

        def _log(self, msg: str, tag: str = "INFO"):
            def _do():
                self.log_area.configure(state="normal")
                self.log_area.insert("end", msg + "\n", tag)
                self.log_area.see("end")
                self.log_area.configure(state="disabled")
            self.root.after(0, _do)

        def _add_files(self):
            exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
            paths = filedialog.askopenfilenames(
                title=_t("select_video"),
                filetypes=[(_t("video_files"), exts), (_t("all_files"), "*.*")],
            )
            for p in paths:
                if p not in self.file_paths:
                    self.file_paths.append(p)
                    self.file_listbox.insert("end", os.path.basename(p))
            self._update_count()

        def _add_directory(self):
            d = filedialog.askdirectory(title=_t("select_dir"))
            if d:
                if d not in self.file_paths:
                    self.file_paths.append(d)
                    self.file_listbox.insert("end", f"{_t('dir_prefix')} {d}")
                self._update_count()

        def _clear_list(self):
            self.file_paths.clear()
            self.file_listbox.delete(0, "end")
            self._update_count()

        def _update_count(self):
            self.file_count_var.set(_t("items", count=len(self.file_paths)))

        def _browse_output(self):
            d = filedialog.askdirectory(title=_t("select_output"))
            if d:
                self.output_dir_var.set(d)

        def _show_about(self):
            from tkinter import messagebox
            messagebox.showinfo(
                _t("about"),
                _t("about_text", version=__version__),
            )

        def _toggle_deadvert(self):
            enabled = self.deadvert_var.get()
            state = "readonly" if enabled else "disabled"
            entry_state = "normal" if enabled else "disabled"
            self.deadvert_method_cb.configure(state=state)
            self.deadvert_min_dur_entry.configure(state=entry_state)

        def _show_deadvert_confirm(self, dv_summary):
            """Show a modal dialog for deadvert confirmation. Thread-safe."""
            result_event = threading.Event()
            user_choice = [False]

            def _show():
                dlg = tk.Toplevel(self.root)
                dlg.title(_t("deadvert_confirm_title"))
                dlg.transient(self.root)
                dlg.grab_set()
                dlg.minsize(500, 350)

                # Treeview with detected segments
                tree_frame = ttk.Frame(dlg, padding=10)
                tree_frame.pack(fill="both", expand=True)

                tree = ttk.Treeview(
                    tree_frame,
                    columns=("start", "end", "duration"),
                    show="tree headings", height=12,
                )
                tree.heading("start", text="Start")
                tree.heading("end", text="End")
                tree.heading("duration", text="Duration")
                tree.column("start", width=100)
                tree.column("end", width=100)
                tree.column("duration", width=80)

                for r in dv_summary.results:
                    if r.ad_segments:
                        vid_id = tree.insert(
                            "", "end",
                            text=os.path.basename(r.video_path),
                            open=True,
                        )
                        for ad in r.ad_segments:
                            tree.insert(
                                vid_id, "end", text="",
                                values=(
                                    format_timestamp(ad.start),
                                    format_timestamp(ad.end),
                                    f"{ad.end - ad.start:.1f}s",
                                ),
                            )

                sb = ttk.Scrollbar(tree_frame, orient="vertical",
                                   command=tree.yview)
                tree.configure(yscrollcommand=sb.set)
                tree.pack(side="left", fill="both", expand=True)
                sb.pack(side="right", fill="y")

                # Summary label
                ttk.Label(
                    dlg,
                    text=_t("deadvert_total_removed",
                            time=dv_summary.total_time_removed),
                    padding=5,
                ).pack()

                # Buttons
                btn_frame = ttk.Frame(dlg, padding=10)
                btn_frame.pack()

                def _proceed():
                    user_choice[0] = True
                    dlg.destroy()
                    result_event.set()

                def _cancel():
                    user_choice[0] = False
                    dlg.destroy()
                    result_event.set()

                ttk.Button(
                    btn_frame, text=_t("deadvert_proceed"),
                    command=_proceed,
                ).pack(side="left", padx=10)
                ttk.Button(
                    btn_frame, text=_t("deadvert_cancel_trim"),
                    command=_cancel,
                ).pack(side="left", padx=10)

                dlg.protocol("WM_DELETE_WINDOW", _cancel)

            self.root.after(0, _show)
            result_event.wait()
            return user_choice[0]

        def _detect_hw_on_startup(self):
            def _detect():
                try:
                    check_ffmpeg()
                    encoders = detect_hw_encoders()
                    hw = [k for k, v in encoders.items() if v and k not in (
                        "libx264", "libx265", "libmp3lame", "aac", "libvpx")]
                    if hw:
                        self.root.after(0, lambda: self.hw_label_var.set(
                            ", ".join(sorted(hw))))
                        self._log(_t("hw_detected", encoders=", ".join(sorted(hw))), "DONE")
                    else:
                        self.root.after(0, lambda: self.hw_label_var.set(
                            _t("none_sw_only")))
                        self._log(_t("no_hw"), "WARN")
                except RuntimeError as e:
                    self.root.after(0, lambda: self.hw_label_var.set(_t("ffmpeg_not_found")))
                    self._log(f"ERROR: {e}", "ERROR")
                    self.root.after(0, lambda: self.start_btn.configure(state="disabled"))

            threading.Thread(target=_detect, daemon=True).start()

        def _start(self):
            if not self.file_paths:
                from tkinter import messagebox
                messagebox.showwarning(_t("no_files_title"), _t("no_files_msg"))
                return

            preset = self.preset_var.get()
            output_dir = self.output_dir_var.get()
            recursive = self.recursive_var.get()
            dry_run = self.dryrun_var.get()

            crf_str = self.crf_var.get().strip()
            crf = int(crf_str) if crf_str.isdigit() else None
            fps_str = self.fps_var.get().strip()
            fps = int(fps_str) if fps_str.isdigit() else 10
            width_str = self.width_var.get().strip()
            width = int(width_str) if width_str.isdigit() else None
            audio_fmt = self.audio_fmt_var.get()
            encoder = self.encoder_var.get().strip() or None
            resolution = self.resolution_var.get().strip() or None
            bitrate = self.bitrate_var.get().strip() or None
            vfps_str = self.video_fps_var.get().strip()
            video_fps = int(vfps_str) if vfps_str.isdigit() else None

            self.cancel_event.clear()
            self.start_btn.configure(state="disabled")
            self.cancel_btn.configure(state="normal")
            self.file_progress_var.set(0)
            self.overall_progress_var.set(0)
            self.file_progress_label.set("0%")
            self.overall_progress_label.set("0%")

            self._log(_t("starting_batch", preset=preset, output=output_dir), "INFO")

            def _worker():
                files = collect_input_files(self.file_paths, recursive)
                if not files:
                    self._log(_t("no_video_found"), "ERROR")
                    self.root.after(0, self._on_complete, None)
                    return

                self._log(_t("found_files", count=len(files)), "INFO")
                out_dir = Path(output_dir)
                out_dir.mkdir(parents=True, exist_ok=True)

                def _logmsg(msg):
                    verbose = self.verbose_var.get()
                    if verbose or not (
                        msg.startswith("frame=") or msg.startswith("size=")
                    ):
                        tag = "INFO"
                        if "[DONE]" in msg:
                            tag = "DONE"
                        elif "[FAIL]" in msg or "ERROR" in msg:
                            tag = "ERROR"
                        self._log(msg, tag)

                # -- Deadvert preprocessing --
                use_deadvert = self.deadvert_var.get()
                if use_deadvert:
                    video_paths = [str(f) for f, _ in files]
                    dv_method = self.deadvert_method_var.get()
                    dv_min_str = self.deadvert_min_dur_var.get().strip()
                    try:
                        dv_min_dur = float(dv_min_str)
                    except ValueError:
                        dv_min_dur = 5.0

                    dv_summary = run_deadvert(
                        video_paths,
                        method=dv_method,
                        threshold=2,
                        min_duration=dv_min_dur,
                        output_dir=str(out_dir),
                        confirm_cb=self._show_deadvert_confirm,
                        log_cb=_logmsg,
                        cancel_event=self.cancel_event,
                    )

                    if self.cancel_event.is_set():
                        self.root.after(0, self._on_complete, None)
                        return

                    if dv_summary.total_ads_found > 0:
                        self._log(
                            _t("deadvert_found",
                                count=dv_summary.total_ads_found,
                                videos=dv_summary.videos_with_ads),
                            "DONE",
                        )

                    # Replace files with trimmed outputs for transcoding
                    trimmed_files = []
                    for r in dv_summary.results:
                        if r.trimmed_output and os.path.isfile(r.trimmed_output):
                            trimmed_files.append(
                                (Path(r.trimmed_output), Path(".")))
                        else:
                            trimmed_files.append(
                                (Path(r.video_path), Path(".")))
                    files_to_use = trimmed_files
                else:
                    files_to_use = files

                jobs = []
                for f, rel_subdir in files_to_use:
                    out = build_output_path(
                        f, out_dir, preset, audio_fmt,
                        relative_subdir=rel_subdir,
                    )
                    job = TranscodeJob(
                        input_path=str(f),
                        output_path=str(out),
                        preset=preset,
                        options={
                            "encoder": encoder,
                            "crf": crf,
                            "fps": fps,
                            "width": width,
                            "audio_format": audio_fmt,
                            "resolution": resolution,
                            "bitrate": bitrate,
                            "video_fps": video_fps,
                        },
                    )
                    jobs.append(job)

                def _progress(file_pct, overall_pct, idx):
                    self.root.after(0, lambda: self.file_progress_var.set(
                        max(0, file_pct)))
                    self.root.after(0, lambda: self.overall_progress_var.set(
                        overall_pct))
                    self.root.after(0, lambda: self.file_progress_label.set(
                        f"{max(0, file_pct):.1f}%  file {idx + 1}/{len(jobs)}"))
                    self.root.after(0, lambda: self.overall_progress_label.set(
                        f"{overall_pct:.1f}%"))

                summary = run_batch(
                    jobs, _progress, _logmsg, self.cancel_event, dry_run,
                )
                self.root.after(0, self._on_complete, summary)

            self.worker_thread = threading.Thread(target=_worker, daemon=True)
            self.worker_thread.start()

        def _cancel(self):
            self.cancel_event.set()
            self._log(_t("cancel_requested"), "WARN")
            self.cancel_btn.configure(state="disabled")

        def _on_complete(self, summary: Optional[BatchSummary]):
            self.start_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")

            if summary is None:
                return

            self.file_progress_var.set(100)
            self.overall_progress_var.set(100)

            msg = (
                f"{_t('batch_complete')}\n\n"
                f"{_t('done')}: {summary.done}\n"
                f"{_t('failed')}: {summary.failed}\n"
                f"{_t('skipped')}: {summary.skipped}\n"
                f"{_t('time_elapsed')}: {summary.elapsed:.1f}s"
            )
            if summary.failed_files:
                msg += f"\n\n{_t('failed_files')}:\n" + "\n".join(
                    f"  - {os.path.basename(f)}" for f in summary.failed_files
                )

            self._log(
                "\n" + _t("batch_summary",
                           done=summary.done, failed=summary.failed,
                           skipped=summary.skipped, elapsed=summary.elapsed),
                "DONE" if summary.failed == 0 else "WARN",
            )

            from tkinter import messagebox
            messagebox.showinfo(_t("batch_complete_title"), msg)

    root = tk.Tk()
    app = TranscoderGUI(root)
    root.mainloop()


# ============================================================================
# Main entry point
# ============================================================================


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.gui or (not args.input and not args.preset
                    and not getattr(args, "deadvert", False)):
        launch_gui()
    else:
        if not args.preset and not getattr(args, "deadvert", False):
            parser.error("--preset or --deadvert is required in CLI mode")
        if not args.input:
            parser.error("No input files or directories specified")
        sys.exit(run_cli(args))


if __name__ == "__main__":
    main()
