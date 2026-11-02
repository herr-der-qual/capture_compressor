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

The pure logic (output naming, skip rules, ffmpeg arguments, verification decision)
lives in `capture_compressor/logic.py` and is covered by `tests/`. Set
`CAPTURE_COMPRESSOR_HOME` to a temporary folder to keep test runs away from your real
settings.

A one-file exe with PyInstaller is planned but not set up yet.

## License

MIT
