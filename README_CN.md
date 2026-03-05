# LaPian (拉片)

[![PyPI version](https://img.shields.io/pypi/v/lapian.svg)](https://pypi.org/project/lapian/)
[![Python](https://img.shields.io/pypi/pyversions/lapian.svg)](https://pypi.org/project/lapian/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

一个单文件 Python 批量视频转码工具，支持硬件加速编码。提供命令行（CLI）和图形界面（tkinter GUI）两种使用方式。

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install lapian
```

安装后可直接使用 `lapian` 命令：

```bash
lapian -p android video.mp4
lapian --gui
```

### 从源码安装

```bash
git clone https://github.com/cycleuser/LaPian.git
cd LaPian
pip install .
```

或直接运行脚本（无需安装）：

```bash
python lapian.py
```

## 功能特性

- **4 种输出预设**：GIF、Android 兼容 MP4、最小体积 MP4、纯音频提取
- **硬件加速**：自动检测 NVENC、QSV、AMF、VAAPI、VideoToolbox 编码器，自动回退到软件编码
- **批量处理**：支持多文件或整个目录（默认递归搜索，保留目录结构）的批量转码
- **双界面**：完整的命令行和 tkinter 图形界面
- **中文支持**：自动检测系统语言，中文环境下 GUI 和命令行输出自动切换为中文
- **进度追踪**：实时显示单文件和总体进度
- **预览模式**：Dry-run 模式可预览 FFmpeg 命令而不实际执行
- **跨平台**：支持 Linux、macOS 和 Windows

## 环境要求

- **Python 3.8+**（需包含 tkinter，大多数 Python 安装默认包含）
- **FFmpeg**（包括 ffprobe）已安装并在系统 PATH 中

### 安装 FFmpeg

| 操作系统 | 安装命令 |
|---|---|
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` |
| Arch Linux | `sudo pacman -S ffmpeg` |
| macOS (Homebrew) | `brew install ffmpeg` |
| Windows | 从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载并添加到 PATH |

### 安装 tkinter（如未安装）

| 操作系统 | 安装命令 |
|---|---|
| Ubuntu/Debian | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| macOS (Homebrew) | `brew install python-tk` |

## 快速开始

### 图形界面模式

启动图形界面：

```bash
lapian --gui
```

或直接运行脚本（不带参数）：

```bash
python lapian.py
```

### 命令行模式

```bash
lapian -p <预设> [选项] <输入文件或目录...>
```

## 命令行参数说明

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `input` | 位置参数 | *（必需）* | 输入的视频文件或目录 |
| `-p`, `--preset` | 选择 | *（必需）* | 预设：`gif`、`android`、`minsize`、`audio` |
| `-o`, `--output` | 路径 | `./transcoded` | 输出目录 |
| `-r`, `--recursive` | 标志 | `true` | 递归搜索目录（默认开启） |
| `--no-recursive` | 标志 | `false` | 禁用递归目录搜索 |
| `--encoder` | 字符串 | *（自动）* | 强制指定编码器（如 `h264_nvenc`） |
| `--crf` | 整数 | *（预设默认）* | 覆盖 CRF 质量值 |
| `--fps` | 整数 | `10` | GIF 帧率 |
| `--width` | 整数 | *（原始）* | 最大输出宽度（像素） |
| `--audio-format` | 选择 | `mp3` | 音频格式：`mp3` 或 `aac` |
| `--dry-run` | 标志 | `false` | 仅打印 FFmpeg 命令，不执行 |
| `--gui` | 标志 | `false` | 启动图形界面 |
| `-v`, `--verbose` | 标志 | `false` | 显示详细的 FFmpeg 输出 |
| `--version` | 标志 | | 显示版本号并退出 |

### 使用示例

**将视频转换为 Android 兼容的 MP4：**
```bash
lapian -p android video.mp4
```

**将目录下所有视频转换为 GIF（15fps，320px 宽）：**
```bash
lapian -p gif --fps 15 --width 320 /path/to/videos/
```

**批量创建最小体积 MP4：**
```bash
lapian -p minsize -o ./compressed video1.mp4 video2.mkv video3.avi
```

**提取音频为 AAC 格式：**
```bash
lapian -p audio --audio-format aac movie.mkv
```

**预览命令（Dry Run 模式）：**
```bash
lapian -p android --dry-run video.mp4
```

**强制使用指定的硬件编码器：**
```bash
lapian -p android --encoder h264_nvenc video.mp4
```

## 预设详情

### `gif` - 动画 GIF

使用 FFmpeg 的两遍调色板优化将视频转换为高质量动画 GIF。

| 参数 | 默认值 | 说明 |
|---|---|---|
| FPS | 10 | 越低 = 文件越小，帧数越少 |
| 宽度 | 480 | 高度自动按比例计算 |

- 使用 `palettegen` + `paletteuse` 实现最优色彩质量
- Bayer 抖动算法实现平滑渐变
- 无音频（GIF 格式限制）

### `android` - Android 兼容 MP4

生成 H.264 Baseline Profile 视频和 AAC 音频，保证在所有 Android 设备上原生播放。

| 参数 | 默认值 | 说明 |
|---|---|---|
| CRF | 23 | 越低 = 质量越好，文件越大 |
| 视频编码 | H.264 (Baseline) | Level 3.1，yuv420p 像素格式 |
| 音频编码 | AAC | 立体声，128 kbps |

- 自动检测硬件编码器（NVENC > QSV > AMF > VAAPI > VideoToolbox > libx264）
- MP4 容器带 `faststart` 标志，支持流式播放
- 兼容几乎所有 Android 设备和网页浏览器

### `minsize` - 最小体积 MP4

激进压缩视频以获得最小文件体积，同时保持可接受的画质。

| 参数 | 默认值 | 说明 |
|---|---|---|
| CRF | 28 | 比 android 预设更高，压缩更强 |
| 视频编码 | H.265/HEVC 优先 | HEVC 不可用时回退到 H.264 CRF 30 |
| 音频编码 | AAC | 单声道，96 kbps |
| 最大高度 | 720p | 源视频超过 720p 时自动缩小 |

- HEVC 编码器链：hevc_nvenc > hevc_qsv > hevc_amf > hevc_vaapi > hevc_videotoolbox > libx265
- 单声道低码率音频进一步缩减体积
- 适用于归档、即时通讯分享或存储空间有限的场景

### `audio` - 音频提取

从视频文件中提取音频轨道。

| 参数 | 默认值 | 说明 |
|---|---|---|
| 格式 | MP3 | 也支持 AAC（使用 `--audio-format aac`） |
| 码率 | 128 kbps | 语音和音乐的良好质量 |

- MP3 输出使用 libmp3lame 编码器
- AAC 输出保存为 `.m4a` 容器

## 硬件加速

LaPian 在启动时自动检测可用的硬件编码器并选择最优选项。检测优先级如下：

### H.264 编码器链
1. `h264_nvenc`（NVIDIA GPU）
2. `h264_qsv`（Intel Quick Sync）
3. `h264_amf`（AMD GPU）
4. `h264_vaapi`（Linux VA-API）
5. `h264_videotoolbox`（macOS）
6. `libx264`（软件编码回退）

### H.265/HEVC 编码器链（minsize 预设）
1. `hevc_nvenc`（NVIDIA GPU）
2. `hevc_qsv`（Intel Quick Sync）
3. `hevc_amf`（AMD GPU）
4. `hevc_vaapi`（Linux VA-API）
5. `hevc_videotoolbox`（macOS）
6. `libx265`（软件编码回退）

使用 `--encoder <名称>` 可强制指定编码器。

## 图形界面使用说明

1. 启动：`lapian --gui`（或 `python lapian.py` 不带参数）
2. 点击**添加文件**或**添加目录**添加视频
3. 从下拉菜单选择**预设**
4. 根据需要调整选项（CRF、FPS、宽度等）
5. 设置**输出目录**
6. 点击**开始转码**
7. 在进度条和日志区域监控进度
8. 点击**取消**可停止当前批次

图形界面在启动时会显示检测到的硬件编码器，并提供转码过程的实时日志。

## 支持的输入格式

MP4、MKV、AVI、MOV、WebM、FLV、WMV、TS、M4V、3GP、MPG、MPEG、VOB、OGV、M2TS、MTS、F4V、RM、RMVB

## 输出文件结构

输出文件保留原始目录结构，放置在输出目录中：

```
<输出目录>/<相对子目录>/<原始文件名>_<预设>.<扩展名>
```

示例：
- `transcoded/myvideo_android.mp4`
- `transcoded/子目录/clip_gif.gif`
- `transcoded/myvideo_minsize.mp4`
- `transcoded/myvideo_audio.mp3`

重名文件自动添加 `_1`、`_2` 等后缀。

## 返回结果说明

### 命令行退出码

| 退出码 | 含义 |
|---|---|
| 0 | 所有任务成功完成 |
| 1 | 一个或多个任务失败 |

### 批处理结果摘要

每次批处理完成后，程序会输出摘要信息，包括：

- **Done（完成）**：成功转码的文件数
- **Failed（失败）**：转码失败的文件数
- **Skipped（跳过）**：因取消操作而跳过的文件数
- **总耗时**：批处理总用时
- **失败文件列表**：如有失败，会列出具体文件路径

## 许可证

本项目采用 GPL-3.0-or-later 许可证。详见 [LICENSE](LICENSE) 文件。
