## PowerTrim

PowerTrim is a fast, modern, segment-based video trimmer built with PySide6 and python-mpv, inspired by LosslessCut. It provides frame-accurate segment management, quick preview, and multiple export modes powered by FFmpeg and optional SmartCut.

### Highlights
- **Interactive trimming UI** with thumbnails, timeline zoom, hover scrub, and keyboard shortcuts
- **Segment management** list with multi-select, color tags, merge, delete, and inline property edits
- **Export modes**: Lossless Copy (remux), Smart Cut (frame-accurate without re-encode), Re-encode (H.264/AAC), Archival FFV1
- **Track selection** for audio/subtitle with language priority and default disposition
- **Auto-crop black bars** detection (FFmpeg `cropdetect`) in re-encode modes
- **Quick snapshots** with configurable directory, format, and filename template
- **EDL Preview**: play all segments externally in mpv without rendering
- **Project save/load** with a simple JSON schema

---

## Requirements

- **Python**: 3.10+ (uses `dict | None` union syntax)
- **FFmpeg**: `ffmpeg` and `ffprobe` must be in PATH
- **mpv** player: required for playback and EDL preview
- Python packages:
  - `PySide6`
  - `python-mpv`
  - Optional for Smart Cut export: the `smartcut` CLI

### Windows quick install tips
- FFmpeg: install with Chocolatey: `choco install ffmpeg` or download from the official site and add to PATH
- mpv: `choco install mpv` or download a portable build and add its folder to PATH
- Python packages:
```bash
pip install PySide6 python-mpv
# Optional (Smart Cut):
pip install smartcut
```

Note: The repo includes a `smartcut/` directory with source for reference, but the GUI uses the external `smartcut` CLI when the Smart Cut mode is selected. Installing via `pip install smartcut` (or another supported method) is recommended so that `smartcut` is available on PATH.

---

## Running the app

```bash
python PowerTrimGUI.py
```

1) Open a video: File → Open Video… (Ctrl+O)
2) Navigate with controls or shortcuts, mark ranges using I/O
3) Each completed I→O creates a segment
4) Manage segments in the dock (rename, change color, merge, delete)
5) Export: File → Export Video…

---

## UI and workflow

### Timeline & thumbnails
- Thumbnails are generated via FFmpeg and cached in `.powertrim_cache/thumbs` alongside the source video
- Hover scrub: when paused, moving the mouse over the timeline shows frames under cursor (toggle in Settings)
- Zoom: use the slider or shortcuts to zoom the timeline

### Segment management
- List shows segment name, frame range, and duration
- Selecting one segment shows editable properties (name, start/end frame)
- Multi-select supports delete and merge (adjacent/overlapping)

### Export dialog
- Modes:
  - Lossless Copy (fast remux)
  - Smart Cut (frame-accurate without re-encode; requires `smartcut`)
  - Re-encode (H.264/AAC; enables auto-crop)
  - Archival (FFV1; lossless video, copy audio/subs)
- Options: Merge into single file or create separate clips, auto-crop black bars (re-encode only)
- Track & language selection: choose which audio/subtitle tracks to include; language priority sets default disposition

### Preview all segments in mpv (EDL)
- Tools → Play All builds an EDL URI and launches external `mpv` to preview all segments back-to-back without export
- Uses a safe link in `.powertrim_cache` if possible

---

## Keyboard shortcuts

### File Operations
- **Ctrl+O** - Open Video
- **Ctrl+S** - Save Project
- **Ctrl+E** - Export Video
- **Ctrl+Q** - Quit

### Playback Control
- **Space** - Play/Pause
- **Left/Right** - Seek 5 seconds
- **Up/Down** - Seek 1 minute
- **,** - Previous frame
- **.** - Next frame
- **Home** - Jump to start
- **End** - Jump to end
- **Ctrl+Left/Right** - Previous/Next boundary

### Segment Management
- **I** - Mark In Point
- **O** - Mark Out Point
- **Delete** - Delete selected segment
- **M** - Merge selected segments
- **Enter** - Play selected segment
- **Ctrl+Enter** - Play all segments

### Timeline Navigation
- **Ctrl+Plus** - Zoom in
- **Ctrl+Minus** - Zoom out
- **Ctrl+0** - Zoom fit
- **Ctrl+Mouse Wheel** - Zoom timeline

### Snapshots
- **F12** - Quick snapshot
- **Ctrl+F12** - Save snapshot as

### Other
- **F1** - Help & About
- **F5** - Refresh thumbnails
- **Ctrl+,** - Settings
- **Ctrl+Z** - Undo
- **Ctrl+Y** - Redo

### MPV Default Shortcuts
The application also supports standard MPV shortcuts:
- **f** - Toggle fullscreen
- **m** - Mute
- **0-9** - Seek to percentage (0% to 90%)
- **[**/**]** - Decrease/Increase playback speed
- **z** - Toggle zoom
- **+**/**-** - Volume up/down
- And many more standard MPV shortcuts

---

## Settings

Edit → Settings…
- Export:
  - Default output directory
  - Default export mode (Copy, Smart Cut, Re-encode, FFV1)
  - Language priority (e.g., `eng,jpn,ger`)
- Snapshots:
  - Quick snapshot directory and format (PNG/JPEG)
  - Filename template supports `{filename}`, `{frame_num}`, `{time_ms}`
- Playback:
  - Enable/disable hover scrub on the timeline

Settings are stored via `QSettings` under organization `PowerTrim`, application `PowerTrimGUI`.

---

## Data formats

### Project JSON
Saved with File → Save Project As…
```json
{
  "video_path": "C:/path/to/video.mp4",
  "segments": [
    {"start_frame": 120, "end_frame": 240, "color": "#ff5757", "name": "Segment [120-240]"}
  ]
}
```

### CSV import
- Import expects at least two integer columns per row: `start_frame,end_frame,...`
- Each row becomes a segment; colors are assigned in a cycling palette

### CSV export
Produced with File → Export → Export Segments to CSV…
```csv
start_frame,end_frame,name
120,240,Segment [120-240]
```

---

## Files and architecture

### `PowerTrimGUI.py` (GUI controller)
- Technologies: PySide6, python-mpv
- Key classes:
  - `ProTrimmerWindow`: main window, timeline, thumbnails, toolbar, menus, segment list, export flow
  - `SettingsDialog`: export/snapshot/playback preferences persisted with `QSettings`
  - `ExportDialog`: export options (mode, merge, auto-crop, filenames, tracks)
  - `ExportStatusDialog`: progress UI with overall/current clip progress and elapsed timer
  - `ThumbnailLoader` (in `QThread`): generates cached thumbnails via FFmpeg
  - `ExportWorker` (in `QThread`): calls engine `run_powertrim_job` and bridges progress to UI
  - `SegmentManager`: in-memory segment list with `model_changed` signal
  - Command pattern: `AddSegmentCommand`, `DeleteSegmentCommand`, `UpdateSegmentCommand`, `ImportSegmentsCommand`, `MergeSegmentsCommand` managed by `UndoManager`
- Notable features:
  - Track selection menus populated from mpv `track-list`
  - EDL preview (`play_all_segments`) launches external `mpv`
  - Window title shows dirty state with `*` until project is saved

### `powertrim_engine.py` (export engine)
- Pure backend invoked by the GUI
- Main functions:
  - `sanitize_filename(name)`: cleans up unsafe path characters
  - `get_video_metadata(path)`: uses `ffprobe` to gather streams, fps, duration, resolution
  - `detect_black_bars(path, duration)`: uses FFmpeg `cropdetect` over a 5s sample in the middle
  - `generate_ffmpeg_mapping_args(streams, selected_ids, lang_priority)`: builds `-map` and `-disposition` args
  - `trim_video_segment(...)`: performs segment extraction via FFmpeg or SmartCut
  - `merge_videos(clip_paths, final_output)`: FFmpeg concat demuxer
  - `run_powertrim_job(settings, worker)`: orchestrates clipping, optional merge, and progress reporting
- Export modes:
  - `copy`: `-c copy` remux
  - `smart-cut`: delegates to `smartcut` CLI (`--keep start,end`)
  - `re-encode`: H.264/AAC, enables filters (e.g., crop)
  - `ffv1`: archival lossless video, copy audio/subs

### `icons.py` (icon factory and store)
- `create_icon_from_svg(svg_string, color) -> QIcon`: recolors SVGs by replacing `currentColor`
- `ICON_DATA`: inline SVG catalog used by the GUI to build a consistent, themeable icon set

---

## Troubleshooting

- mpv not found
  - Ensure `mpv` is installed and in PATH; on Windows, `choco install mpv` or add the folder containing `mpv.exe` to PATH
- FFmpeg/ffprobe not found
  - Install FFmpeg and ensure `ffmpeg` and `ffprobe` are in PATH
- Smart Cut disabled or error
  - For some codecs (e.g., VP9 HDR profiles), Smart Cut is disabled by the UI. Otherwise install the `smartcut` CLI
- Thumbnails never appear
  - FFmpeg is required to generate thumbnails; check PATH
- Unicode/long filenames
  - Filenames are sanitized via `sanitize_filename()` before export; adjust templates if needed

---

## Portable build (Windows)

Create a zero-install ZIP that includes all dependencies and tools.

### Folder layout

```
PowerTrim/
  PowerTrim.exe
  portable_mode                 # empty file enables INI settings in app folder
  PowerTrim.ini                 # created on first run in portable mode
  bin/
    ffmpeg.exe
    ffprobe.exe
    mpv.exe
    libmpv-2.dll
    smartcut.exe                # included as requested
  licenses/                     # include FFmpeg/mpv/smartcut licenses
  ... (Qt runtime files from PyInstaller)
```

### Build steps

1) In a clean venv:
```bash
pip install PySide6 python-mpv pyinstaller smartcut
```

2) Place Windows binaries in `bin/` (ffmpeg, ffprobe, mpv, libmpv-2.dll, smartcut)

3) Package with PyInstaller (onedir recommended):
```bash
pyinstaller --noconfirm --clean --name PowerTrim \
  --add-binary "bin/ffmpeg.exe;bin" \
  --add-binary "bin/ffprobe.exe;bin" \
  --add-binary "bin/mpv.exe;bin" \
  --add-binary "bin/libmpv-2.dll;bin" \
  --add-binary "bin/smartcut.exe;bin" \
  PowerTrimGUI.py
```

4) In the dist folder, add an empty `portable_mode` file next to `PowerTrim.exe`. The app will use `PowerTrim.ini` (INI settings) in the same folder, and default output/snapshot directories under the app folder.

5) Zip the `PowerTrim/` folder and distribute.

Notes:
- The app resolves tools via `bin/` first, then PATH. EDL preview uses the bundled `mpv.exe` when present.
- Include third-party licenses in `licenses/` to satisfy GPL/LGPL obligations.

## Notes and conventions

- Output templates support placeholders like `{filename}`, `{num}`, `{num:03d}`, `{start}`, `{end}`, `{date}`, `{time}`, `{resolution}` (see engine)
- When merging, clips are rendered to a temp directory and concatenated via manifest; non-merge writes each clip directly to the chosen output folder
- Archival FFV1 outputs `.mkv`, Re-encode outputs `.mp4`; Copy and Smart Cut retain the source container unless otherwise specified by the template/selection

---

## License

No license file is provided. If you intend to publish or distribute, add an appropriate license.


