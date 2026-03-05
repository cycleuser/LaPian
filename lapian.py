#!/usr/bin/env python3
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

__version__ = "1.1.0"

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


def _get_hw_quality_flags(encoder: str, crf: int) -> list:
    """Return encoder-specific quality flags."""
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


def _build_scale_filter(width: Optional[int], cap_height: Optional[int] = None) -> list:
    """Build a -vf scale filter string. Returns [] if no scaling needed."""
    filters = []
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
    width: Optional[int] = None, **kwargs,
) -> list:
    """Build Android-compatible MP4 command."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(input_path),
        "-c:v", encoder,
    ]
    cmd.extend(_get_hw_quality_flags(encoder, crf))

    if encoder == "libx264":
        cmd.extend(["-profile:v", "baseline", "-level:v", "3.1"])

    vf_parts = _build_scale_filter(width)
    if vf_parts:
        cmd.extend(["-vf", ",".join(vf_parts)])

    cmd.extend([
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart",
        str(output_path),
    ])
    return [(cmd, "Encoding Android MP4", None)]


def build_minsize_command(
    input_path: str, output_path: str,
    encoder: str = "libx265", crf: int = 28,
    width: Optional[int] = None,
    probe_data: Optional[dict] = None, **kwargs,
) -> list:
    """Build minimum-size MP4 command."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(input_path),
        "-c:v", encoder,
    ]
    cmd.extend(_get_hw_quality_flags(encoder, crf))

    vf_parts = _build_scale_filter(width)
    if not vf_parts and probe_data and probe_data.get("height", 0) > 720:
        vf_parts = ["scale=-2:720"]
    if vf_parts:
        cmd.extend(["-vf", ",".join(vf_parts)])

    cmd.extend([
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ac", "1",
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
        )
        if log_cb:
            log_cb(f"  Using encoder: {enc}")
    elif job.preset == "minsize":
        enc = select_encoder(HEVC_CHAIN, available, encoder_override)
        if enc == "libx265" and not available.get("libx265", False):
            enc = select_encoder(H264_CHAIN, available, encoder_override)
            crf = crf_val if crf_val is not None else 30
        else:
            crf = crf_val if crf_val is not None else 28
        commands = build_minsize_command(
            job.input_path, job.output_path,
            encoder=enc, crf=crf, width=width_val,
            probe_data=probe_data,
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

    encoders = detect_hw_encoders()
    hw_available = [k for k, v in encoders.items() if v and k not in (
        "libx264", "libx265", "libmp3lame", "aac", "libvpx")]
    if hw_available:
        print(_t("hw_detect_cli", encoders=", ".join(hw_available)))
    else:
        print(_t("no_hw_cli"))

    files = collect_input_files(args.input, not args.no_recursive)
    if not files:
        print(_t("no_video_cli"), file=sys.stderr)
        return 1
    print(_t("found_cli", count=len(files)))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

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
            },
        )
        jobs.append(job)

    cancel_event = threading.Event()

    def cli_progress(file_pct, overall_pct, idx):
        bar_len = 30
        filled = int(bar_len * max(0, file_pct) / 100)
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stderr.write(
            f"\r  [{bar}] {file_pct:5.1f}%  (overall: {overall_pct:.1f}%)"
        )
        sys.stderr.flush()

    def cli_log(msg):
        if args.verbose or not msg.startswith("frame="):
            print(msg, file=sys.stderr)

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
            self.root.title(f"LaPian (拉片) v{__version__}")
            self.root.minsize(950, 680)
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(2, weight=1)

            self.cancel_event = threading.Event()
            self.worker_thread = None
            self.file_paths = []

            self._build_ui()
            self._detect_hw_on_startup()

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
                font=("Consolas", 9),
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
                font=("Consolas", 9), wrap="word",
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

                jobs = []
                for f, rel_subdir in files:
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

    if args.gui or (not args.input and not args.preset):
        launch_gui()
    else:
        if not args.preset:
            parser.error("--preset is required in CLI mode")
        if not args.input:
            parser.error("No input files or directories specified")
        sys.exit(run_cli(args))


if __name__ == "__main__":
    main()
