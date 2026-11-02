# Capture Compressor

A small Windows tray app that watches your screen-recordings folder (Xbox Game Bar
saves to `%USERPROFILE%\Videos\Captures` by default), compresses every new recording
with ffmpeg and removes the big original once the compressed copy is verified.

- `Clip.mp4` becomes `Clip.compressed.mp4` next to it. Files with `.compressed` in the
  name are never touched again.
- It waits until a recording is finished: the file size has to stop changing and no
  other program may have the file open (Game Bar keeps it open while recording).
- Resolution, frame timing and audio are kept; only the video is re-encoded.
- The original is deleted only after checking the result: ffprobe can read it, the
  duration matches (within 1%, at least 0.5 s) and it is actually smaller. If the
  output is not smaller, the original is kept and the output is dropped.
- Originals go to the Recycle Bin by default (permanent deletion is a setting).
- Recordings that were already in the folder are processed on startup.

## Requirements

- Windows 10/11
- Python 3.10+ (developed with 3.14)
- [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (with ffprobe) on `PATH`, or point the app
  to it in Settings

## Install

```bash
git clone git@github.com:herr-der-qual/capture_compressor.git
cd capture_compressor
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```bash
.venv\Scripts\pythonw capture_compressor.pyw
```

`pythonw` runs it without a console window. A colored icon appears in the tray:

| Color  | Meaning                         |
|--------|---------------------------------|
| green  | idle, watching                  |
| orange | compressing (tooltip shows the file and how many are queued) |
| gray   | paused                          |
| red    | error (e.g. folder or ffmpeg not found), see the log |

Tray menu: **Settings…**, **Pause/Resume**, **Open folder**, **Open log**, **Exit**.
Double-clicking the icon opens Settings.

On first start the app adds itself to *Start with Windows* (per-user `Run` registry
key, no admin rights). Turn it off in Settings.

For a quick test without the tray (logs to the console):

```bash
.venv\Scripts\python -m capture_compressor --once --folder C:\path\to\test\videos
.venv\Scripts\python -m capture_compressor --headless
```

## Settings

Stored in `%APPDATA%\CaptureCompressor\settings.json`; the log is
`%APPDATA%\CaptureCompressor\capture_compressor.log`.

| Setting | Default | Notes |
|---|---|---|
| Watch folder | `%USERPROFILE%\Videos\Captures` | not recursive |
| Encoder | GPU `hevc_nvenc` | alternatives: CPU `libx265`, CPU `libx264` |
| Quality | 28 | CQ for NVENC, CRF for x264/x265; lower = better quality, bigger files |
| ffmpeg location | empty (PATH) | path to `ffmpeg.exe` or its folder; `ffprobe.exe` must be next to it |
| Delete originals permanently | off | off = Recycle Bin |
| Start with Windows | on | |

The chosen encoder is tested with a one-second encode at startup. If it doesn't work
(for example an NVIDIA driver that is too old for your ffmpeg build), the app shows a
notification and uses `libx265` on the CPU instead.

> **NVENC and older GPUs:** ffmpeg 8.1+/9.x builds need NVIDIA driver 610 or newer for
> NVENC. GTX 10xx / TITAN Xp (Pascal) cards don't get those drivers, so with a current
> ffmpeg they fall back to CPU. To use the GPU on such cards, download an older ffmpeg
> build whose NVENC version matches your driver and set it as *ffmpeg location*.

Files that didn't get smaller are remembered in `skipped.json` so they aren't retried
on every start (a changed file is tried again).

## Development

```bash
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest
```

Code layout (`capture_compressor/`):

| Module | Responsibility |
|---|---|
| `decisions.py` | pure rules: output naming, which files to handle, ffmpeg arguments, verification |
| `engine.py` | background worker that ties everything together |
| `folder_watcher.py` | reports new and changed files in the watch folder |
| `recording_queue.py` | waiting recordings; detects when one is finished |
| `compression_job.py` | encode, verify and replace one recording |
| `ffmpeg_tools.py` | finding and running ffmpeg / ffprobe |
| `file_operations.py` | "is another program using this file?", Recycle Bin / delete |
| `settings.py`, `skip_list.py`, `logging_setup.py` | files in `%APPDATA%\CaptureCompressor` |
| `tray.py`, `tray_icon_image.py`, `settings_window.py` | user interface |
| `autostart.py`, `single_instance.py` | Windows integration |

Set `CAPTURE_COMPRESSOR_HOME` to a temporary folder to keep test runs away from your
real settings.

## Build a standalone exe

```bash
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\python build_executable.py
```

This creates `dist\CaptureCompressor.exe` (about 20 MB), a single file that runs
without Python. ffmpeg is not included: it still has to be on `PATH` or set in
Settings. When started from the exe, *Start with Windows* points to the exe itself.

The exe is not code-signed, so Windows SmartScreen may warn about an unknown
publisher on first start.

## License

MIT
