"""LaPian CLI — command-line interface for batch video transcoding."""

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

from . import __version__
from .core import (
    PRESET_NAMES,
    RESOLUTION_CHOICES,
    FPS_CHOICES,
    DEFAULT_OUTPUT_DIR,
    H264_CHAIN,
    check_ffmpeg,
    detect_hw_encoders,
    collect_input_files,
    build_output_path,
    TranscodeJob,
    run_batch,
    run_deadvert,
    format_timestamp,
)
from .i18n import _t


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
        "-V", "--version", action="version",
        version=f"LaPian {__version__}",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress non-error output",
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
    import json as json_mod

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(message)s", stream=sys.stderr,
    )

    json_output = getattr(args, "json_output", False)
    quiet = getattr(args, "quiet", False)

    def _print(*a, **kw):
        if not quiet:
            print(*a, **kw)

    try:
        check_ffmpeg()
    except RuntimeError as e:
        if json_output:
            print(json_mod.dumps({"status": "error", "version": __version__,
                                  "result": None, "errors": [str(e)]}))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    files = collect_input_files(args.input, not args.no_recursive)
    if not files:
        if json_output:
            print(json_mod.dumps({"status": "error", "version": __version__,
                                  "result": None, "errors": [_t("no_video_cli")]}))
        else:
            print(_t("no_video_cli"), file=sys.stderr)
        return 1
    _print(_t("found_cli", count=len(files)))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    cancel_event = threading.Event()

    def cli_log(msg):
        if not quiet and (args.verbose or not msg.startswith("frame=")):
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

        if getattr(args, "detect_only", False):
            if json_output:
                result_data = {
                    "total_ads": dv_summary.total_ads_found,
                    "videos_with_ads": dv_summary.videos_with_ads,
                    "total_time_removed": dv_summary.total_time_removed,
                }
                print(json_mod.dumps({"status": "success", "version": __version__,
                                      "result": result_data, "errors": []}))
            else:
                if dv_summary.total_ads_found == 0:
                    _print(_t("deadvert_no_ads"))
                else:
                    _print(f"\n{_t('deadvert_report_header')}")
                    _print("-" * 50)
                    for r in dv_summary.results:
                        if r.ad_segments:
                            _print(_t("deadvert_report_video",
                                     name=os.path.basename(r.video_path)))
                            for n, ad in enumerate(r.ad_segments, 1):
                                _print(_t("deadvert_report_seg",
                                         n=n,
                                         start=format_timestamp(ad.start),
                                         end=format_timestamp(ad.end),
                                         duration=ad.end - ad.start,
                                         count=len(ad.source_videos) + 1))
                    _print("-" * 50)
                    _print(_t("deadvert_total_removed",
                              time=dv_summary.total_time_removed))
            return 0

        if not args.preset:
            if json_output:
                result_data = {
                    "total_ads": dv_summary.total_ads_found,
                    "videos_with_ads": dv_summary.videos_with_ads,
                    "total_time_removed": dv_summary.total_time_removed,
                }
                print(json_mod.dumps({"status": "success", "version": __version__,
                                      "result": result_data, "errors": []}))
            else:
                _print(f"\n{'='*50}")
                _print(_t("deadvert_found",
                          count=dv_summary.total_ads_found,
                          videos=dv_summary.videos_with_ads))
                _print(_t("deadvert_total_removed",
                          time=dv_summary.total_time_removed))
                _print(f"{'='*50}")
            return 0

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
        if json_output:
            print(json_mod.dumps({"status": "error", "version": __version__,
                                  "result": None, "errors": ["--preset is required for transcoding."]}))
        else:
            print("ERROR: --preset is required for transcoding.", file=sys.stderr)
        return 1

    encoders = detect_hw_encoders()
    hw_available = [k for k, v in encoders.items() if v and k not in (
        "libx264", "libx265", "libmp3lame", "aac", "libvpx")]
    if hw_available:
        _print(_t("hw_detect_cli", encoders=", ".join(hw_available)))
    else:
        _print(_t("no_hw_cli"))

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
        if not quiet:
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

    if not quiet:
        sys.stderr.write("\n")

    if json_output:
        result_data = {
            "total": summary.total,
            "done": summary.done,
            "failed": summary.failed,
            "skipped": summary.skipped,
            "elapsed": round(summary.elapsed, 1),
            "failed_files": summary.failed_files,
        }
        status = "success" if summary.failed == 0 else "error"
        errors = [f"Failed: {f}" for f in summary.failed_files]
        print(json_mod.dumps({"status": status, "version": __version__,
                              "result": result_data, "errors": errors}))
    else:
        _print(f"\n{'='*50}")
        _print(_t("batch_summary", done=summary.done, failed=summary.failed,
                 skipped=summary.skipped, elapsed=summary.elapsed))
        if summary.failed_files:
            _print(_t("failed_files_cli"))
            for fp in summary.failed_files:
                _print(f"  - {fp}")
        _print(f"{'='*50}")

    return 1 if summary.failed > 0 else 0


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.gui or (not args.input and not args.preset
                    and not getattr(args, "deadvert", False)):
        from .gui import launch_gui
        launch_gui()
    else:
        if not args.preset and not getattr(args, "deadvert", False):
            parser.error("--preset or --deadvert is required in CLI mode")
        if not args.input:
            parser.error("No input files or directories specified")
        sys.exit(run_cli(args))


if __name__ == "__main__":
    main()
