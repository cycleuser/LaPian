"""LaPian core — transcoding engine, hardware detection, and ad removal."""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from .i18n import _t

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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
    """Build a -vf scale filter string. Returns [] if no scaling needed."""
    filters = []
    if resolution:
        wh = _RESOLUTION_MAP.get(resolution.lower().strip())
        if wh:
            w, h = wh
        else:
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
    """Build minimum-size MP4 command."""
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
    """Build output file path with appropriate extension."""
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
    """Check if dependencies for the chosen detection method are available."""
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
    """Extract raw chromaprint fingerprints via fpcalc."""
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
    """Find matching segments between two audio fingerprint arrays."""
    RATE = 0.12  # seconds per fingerprint sample
    win_samples = max(int(window_sec / RATE), 10)
    stride = max(win_samples // 2, 1)
    min_match_samples = int(min_match_sec / RATE)

    if len(fp_a) < win_samples or len(fp_b) < win_samples:
        return []

    matches = []

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
    """Extract perceptual hashes for video frames at regular intervals."""
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
    """Find matching segments between two frame hash sequences."""
    if not hashes_a or not hashes_b:
        return []

    b_index = {}
    for ib, (ts_b, hb) in enumerate(hashes_b):
        prefix = hb[:4]
        b_index.setdefault(prefix, []).append(ib)

    pair_matches = {}
    for ia, (ts_a, ha) in enumerate(hashes_a):
        prefix = ha[:4]
        candidates = set()
        for p, ibs in b_index.items():
            if _hamming_hex(prefix, p) <= 4:
                candidates.update(ibs)
        for ib in candidates:
            dist = _hamming_hex(ha, hashes_b[ib][1])
            if dist <= max_hamming:
                pair_matches[(ia, ib)] = dist

    if not pair_matches:
        return []

    # Find diagonal runs
    segments = []
    visited = set()

    for (ia, ib) in sorted(pair_matches.keys()):
        if (ia, ib) in visited:
            continue
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
    """Aggregate matched segments across video pairs to identify ads."""
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

        segs.sort(key=lambda s: s.start)

        merged = [segs[0]]
        for seg in segs[1:]:
            prev = merged[-1]
            if seg.start <= prev.end + 1.0:
                prev.end = max(prev.end, seg.end)
                prev.confidence = max(prev.confidence, seg.confidence)
                for v in seg.source_videos:
                    if v not in prev.source_videos:
                        prev.source_videos.append(v)
            else:
                merged.append(seg)

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
    """Invert ad segments to get the 'keep' regions."""
    if not ad_segments:
        return [(0.0, duration)]

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
    """Trim video to keep only clean segments using ffmpeg stream-copy."""
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
    """Run the full ad detection and removal pipeline."""
    summary = DeadvertSummary(total_videos=len(video_paths))

    def _log(msg):
        if log_cb:
            log_cb(msg)

    if len(video_paths) < 2:
        _log(_t("deadvert_need_multiple"))
        return summary

    ok, err = check_deadvert_deps(method)
    if not ok:
        _log(f"ERROR: {err}")
        return summary

    _log(_t("deadvert_detecting"))

    durations = {}
    has_audio = {}
    for vp in video_paths:
        info = probe_video(vp)
        durations[vp] = info.get("duration", 0)
        has_audio[vp] = info.get("has_audio", True)

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

    ad_map = aggregate_ad_segments(
        all_matches, video_paths, durations,
        threshold=threshold, min_duration=min_duration,
    )

    for vp in video_paths:
        ads = ad_map.get(vp, [])
        dur = durations.get(vp, 0)
        clean = compute_clean_segments(dur, ads)
        dv_result = DeadvertResult(
            video_path=vp,
            ad_segments=ads,
            clean_segments=clean,
        )
        summary.results.append(dv_result)
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

    if confirm_cb is not None:
        if not confirm_cb(summary):
            return summary

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, dv_result in enumerate(summary.results):
        if cancel_event and cancel_event.is_set():
            break

        _log(_t("deadvert_trimming", current=idx + 1, total=len(summary.results)))
        vp = dv_result.video_path
        basename = Path(vp).stem
        ext = Path(vp).suffix
        out_path = str(out_dir / f"{basename}_deadvert{ext}")

        if not dv_result.ad_segments:
            _log(_t("deadvert_no_change", name=os.path.basename(vp)))
            shutil.copy2(vp, out_path)
            dv_result.trimmed_output = out_path
            continue

        total_clean = sum(e - s for s, e in dv_result.clean_segments)
        if total_clean < 1.0:
            _log(_t("deadvert_video_all_ad", name=os.path.basename(vp)))
            continue

        ok, err = trim_video(
            vp, dv_result.clean_segments, out_path,
            cancel_event=cancel_event, log_cb=log_cb,
        )
        if ok:
            dv_result.trimmed_output = out_path
            _log(f"  [DONE] {os.path.basename(out_path)}")
        else:
            _log(f"  [FAIL] {os.path.basename(vp)}: {err}")

    _log(_t("deadvert_total_removed", time=summary.total_time_removed))
    return summary
