# LaPian (拉片)

[![PyPI version](https://img.shields.io/pypi/v/lapian.svg)](https://pypi.org/project/lapian/)
[![Python](https://img.shields.io/pypi/pyversions/lapian.svg)](https://pypi.org/project/lapian/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

A single-file Python tool for batch video transcoding with hardware-accelerated encoding support. Provides both a CLI and a graphical (tkinter) interface.

## Installation

### From PyPI (recommended)

```bash
pip install lapian
```

After installation, use the `lapian` command directly:

```bash
lapian -p android video.mp4
lapian --gui
```

### From source

```bash
git clone https://github.com/cycleuser/LaPian.git
cd LaPian
pip install .
```

Or run the script directly without installing:

```bash
python lapian.py
```

## Features

- **4 output presets**: GIF, Android-compatible MP4, minimum-size MP4, audio-only extraction
- **Hardware acceleration**: Auto-detects NVENC, QSV, AMF, VAAPI, VideoToolbox encoders with software fallback
- **Batch processing**: Transcode multiple files or entire directories (recursive by default, preserves directory structure)
- **Dual interface**: Full-featured CLI and tkinter GUI
- **Chinese support**: Auto-detects system locale, GUI and CLI output in Chinese when appropriate
- **Progress tracking**: Real-time per-file and overall progress
- **Dry-run mode**: Preview FFmpeg commands without executing
- **Cross-platform**: Works on Linux, macOS, and Windows

## Prerequisites

- **Python 3.8+** with tkinter (included in most Python installations)
- **FFmpeg** (including ffprobe) installed and available in PATH

### Installing FFmpeg

| OS | Command |
|---|---|
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` |
| Arch Linux | `sudo pacman -S ffmpeg` |
| macOS (Homebrew) | `brew install ffmpeg` |
| Windows | Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH |

### Installing tkinter (if not already available)

| OS | Command |
|---|---|
| Ubuntu/Debian | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| macOS (Homebrew) | `brew install python-tk` |

## Quick Start

### GUI Mode

Launch the graphical interface:

```bash
lapian --gui
```

Or run the script directly with no arguments:

```bash
python lapian.py
```

### CLI Mode

```bash
lapian -p <preset> [options] <input_files_or_dirs...>
```

## CLI Usage

### Arguments

| Argument | Type | Default | Description |
|---|---|---|---|
| `input` | positional | *(required)* | Input video files or directories |
| `-p`, `--preset` | choice | *(required)* | Preset: `gif`, `android`, `minsize`, `audio` |
| `-o`, `--output` | path | `./transcoded` | Output directory |
| `-r`, `--recursive` | flag | `true` | Recursively search directories (on by default) |
| `--no-recursive` | flag | `false` | Disable recursive directory search |
| `--encoder` | string | *(auto)* | Force a specific encoder (e.g., `h264_nvenc`) |
| `--crf` | int | *(preset default)* | Override CRF quality value |
| `--fps` | int | `10` | GIF framerate |
| `--width` | int | *(original)* | Max output width in pixels |
| `--audio-format` | choice | `mp3` | Audio format: `mp3` or `aac` |
| `--dry-run` | flag | `false` | Print FFmpeg commands without executing |
| `--gui` | flag | `false` | Launch GUI mode |
| `-v`, `--verbose` | flag | `false` | Show detailed FFmpeg output |
| `--version` | flag | | Show version and exit |

### Examples

**Convert a video to Android-compatible MP4:**
```bash
lapian -p android video.mp4
```

**Convert all videos in a directory to GIF (15fps, 320px wide):**
```bash
lapian -p gif --fps 15 --width 320 /path/to/videos/
```

**Create minimum-size MP4 from multiple files:**
```bash
lapian -p minsize -o ./compressed video1.mp4 video2.mkv video3.avi
```

**Extract audio as AAC:**
```bash
lapian -p audio --audio-format aac movie.mkv
```

**Preview commands without executing (dry run):**
```bash
lapian -p android --dry-run video.mp4
```

**Force a specific hardware encoder:**
```bash
lapian -p android --encoder h264_nvenc video.mp4
```

## Preset Details

### `gif` - Animated GIF

Converts video to high-quality animated GIF using FFmpeg's two-pass palette optimization.

| Parameter | Default | Notes |
|---|---|---|
| FPS | 10 | Lower = smaller file, fewer frames |
| Width | 480 | Height auto-calculated to maintain aspect ratio |

- Uses `palettegen` + `paletteuse` for optimal color quality
- Bayer dithering for smooth gradients
- No audio (GIF format limitation)

### `android` - Android-Compatible MP4

Produces H.264 Baseline profile video with AAC audio, guaranteed to play natively on all Android devices.

| Parameter | Default | Notes |
|---|---|---|
| CRF | 23 | Lower = better quality, larger file |
| Video codec | H.264 (Baseline) | Level 3.1, yuv420p pixel format |
| Audio codec | AAC | Stereo, 128 kbps |

- Hardware encoder auto-detected (NVENC > QSV > AMF > VAAPI > VideoToolbox > libx264)
- MP4 container with `faststart` flag for streaming
- Compatible with virtually all Android devices and web browsers

### `minsize` - Minimum Size MP4

Aggressively compresses video for smallest possible file size while maintaining acceptable quality.

| Parameter | Default | Notes |
|---|---|---|
| CRF | 28 | Higher than android preset for more compression |
| Video codec | H.265/HEVC preferred | Falls back to H.264 CRF 30 if HEVC unavailable |
| Audio codec | AAC | Mono, 96 kbps |
| Max height | 720p | Auto-downscales if source exceeds 720p |

- HEVC encoder chain: hevc_nvenc > hevc_qsv > hevc_amf > hevc_vaapi > hevc_videotoolbox > libx265
- Mono audio at reduced bitrate for smaller output
- Ideal for archival, sharing on messaging apps, or limited storage

### `audio` - Audio Extraction

Extracts the audio track from video files.

| Parameter | Default | Notes |
|---|---|---|
| Format | MP3 | Also supports AAC (use `--audio-format aac`) |
| Bitrate | 128 kbps | Good quality for speech and music |

- MP3 output uses libmp3lame encoder
- AAC output saved as `.m4a` container

## Hardware Acceleration

LaPian automatically detects available hardware encoders at startup and selects the best one. The detection order (highest priority first):

### H.264 Encoder Chain
1. `h264_nvenc` (NVIDIA GPU)
2. `h264_qsv` (Intel Quick Sync)
3. `h264_amf` (AMD GPU)
4. `h264_vaapi` (Linux VA-API)
5. `h264_videotoolbox` (macOS)
6. `libx264` (Software fallback)

### H.265/HEVC Encoder Chain (minsize preset)
1. `hevc_nvenc` (NVIDIA GPU)
2. `hevc_qsv` (Intel Quick Sync)
3. `hevc_amf` (AMD GPU)
4. `hevc_vaapi` (Linux VA-API)
5. `hevc_videotoolbox` (macOS)
6. `libx265` (Software fallback)

Use `--encoder <name>` to force a specific encoder if auto-detection doesn't choose the one you want.

## GUI Usage

1. Launch: `lapian --gui` (or `python lapian.py` with no arguments)
2. Click **Add Files** or **Add Directory** to queue videos
3. Select a **Preset** from the dropdown
4. Adjust options (CRF, FPS, width, etc.) as needed
5. Set the **Output Directory**
6. Click **Start Transcoding**
7. Monitor progress in the progress bars and log area
8. Click **Cancel** to stop the current batch

The GUI displays detected hardware encoders at startup and provides real-time logging of the transcoding process.

## Supported Input Formats

MP4, MKV, AVI, MOV, WebM, FLV, WMV, TS, M4V, 3GP, MPG, MPEG, VOB, OGV, M2TS, MTS, F4V, RM, RMVB

## Output Structure

Output files are placed in the output directory, preserving the original directory structure:

```
<output_dir>/<relative_subdir>/<original_name>_<preset>.<ext>
```

Examples:
- `transcoded/myvideo_android.mp4`
- `transcoded/subdir/clip_gif.gif`
- `transcoded/myvideo_minsize.mp4`
- `transcoded/myvideo_audio.mp3`

Duplicate filenames are automatically resolved by appending `_1`, `_2`, etc.

## Exit Codes (CLI)

| Code | Meaning |
|---|---|
| 0 | All jobs completed successfully |
| 1 | One or more jobs failed |

## License

This project is licensed under GPL-3.0-or-later. See the [LICENSE](LICENSE) file for details.
