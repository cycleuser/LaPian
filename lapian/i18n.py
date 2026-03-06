"""LaPian i18n — language detection and translation strings."""

import locale
import os


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
