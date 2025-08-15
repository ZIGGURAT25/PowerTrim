# powertrim_engine.py

import json
import re
import subprocess
import tempfile
import shutil
import sys
import os
from pathlib import Path
from fractions import Fraction
from datetime import datetime

# NOTE: This is the backend engine for PowerTrim. It is designed to be
# imported and used by a GUI or other scripts.

# --- UX Enhancement: Color Class for Terminal Output ---
class Colors:
    HEADER = '\033[95m'; OKBLUE = '\033[94m'; OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'; WARNING = '\033[93m'; FAIL = '\033[91m'
    ENDC = '\033[0m'; BOLD = '\033[1m'; UNDERLINE = '\033[4m'

def cprint(color, message):
    print(f"{color}{message}{Colors.ENDC}")

# ==============================================================================
# --- CORE BACKEND LOGIC (The "Engine") ---
# ==============================================================================

def _get_app_root() -> Path:
    """Return the root folder of the app (EXE folder when frozen, file folder otherwise)."""
    if getattr(sys, 'frozen', False):
        # For PyInstaller builds, the bin directory is in _internal/bin
        exe_dir = Path(sys.executable).resolve().parent
        internal_bin = exe_dir / '_internal' / 'bin'
        if internal_bin.exists():
            return exe_dir / '_internal'
        return exe_dir
    return Path(__file__).resolve().parent

def resolve_tool(tool_name: str) -> str:
    """Resolve an external tool, preferring a bundled binary in `bin/` next to the app.

    - On Windows, automatically tries `<name>.exe` in `bin/`.
    - Falls back to PATH via shutil.which.
    - Returns the original name if no better path is found.
    """
    app_root = _get_app_root()
    bin_dir = app_root / 'bin'

    candidates: list[Path] = []
    base = tool_name
    if os.name == 'nt' and not base.lower().endswith('.exe'):
        base_exe = base + '.exe'
        candidates.append(bin_dir / base_exe)
        # Also consider libmpv-2.dll for mpv/python-mpv scenarios, but executable is primary
    candidates.append(bin_dir / base)

    for cand in candidates:
        if cand.exists():
            return str(cand)

    # PATH fallback
    which_path = shutil.which(base)
    if which_path:
        return which_path
    if os.name == 'nt':
        which_path_exe = shutil.which(base + '.exe')
        if which_path_exe:
            return which_path_exe
    return tool_name

def sanitize_filename(name: str) -> str:
    """Removes illegal characters from a string so it can be a valid filename."""
    name = name.replace('｜', '-').replace('：', ':')
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def get_video_metadata(video_file: Path) -> dict | None:
    """Gets all stream and format metadata from a video file using ffprobe."""
    if not video_file or not video_file.is_file():
        raise FileNotFoundError(f"Input video file not found at '{video_file}'")
    command = [resolve_tool("ffprobe"), "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(video_file)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        data = json.loads(result.stdout)
        
        for i, s in enumerate(data.get("streams", [])):
            s['index'] = i
            s['id'] = s.get('stream_identifier', i)

        video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
        if not video_stream: raise RuntimeError("No video stream found in the file.")
        
        r_frame_rate = video_stream.get("r_frame_rate")
        try:
            data['fps'] = float(Fraction(r_frame_rate)) if r_frame_rate and r_frame_rate != "0/0" else 0
        except Exception:
            data['fps'] = 0
        data['duration'] = float(data.get('format', {}).get('duration', 0))
        data['resolution'] = f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}"
        
        return data
    except FileNotFoundError:
        raise FileNotFoundError("`ffprobe` command not found. Is FFmpeg installed and in your system's PATH?")
    except Exception as e:
        raise RuntimeError(f"Error processing video metadata: {e}")

def detect_black_bars(video_file: Path, duration: float, worker=None) -> str | None:
    if worker: worker.step_changed.emit("Analyzing for black bars...")
    else: cprint(Colors.OKBLUE, "> Analyzing video for black bars...")
    
    seek_point = duration / 3
    command = [resolve_tool("ffmpeg"), "-ss", str(seek_point), "-i", str(video_file), "-t", "5", "-vf", "cropdetect", "-f", "null", "-"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        output = result.stderr
        crop_filter = re.findall(r"crop=\d+:\d+:\d+:\d+", output)
        if crop_filter:
            detected_crop = crop_filter[-1]
            if worker: worker.step_changed.emit(f"Detected crop: {detected_crop}")
            else: cprint(Colors.OKCYAN, f"  [i] Detected crop parameters: {detected_crop}")
            return detected_crop
        return None
    except FileNotFoundError:
        raise FileNotFoundError("`ffmpeg` command not found. Is FFmpeg installed and in your PATH?")

def convert_seconds_to_hhmmss(seconds: float) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds_val = divmod(remainder, 60)
    return f"{int(hours):02}:{int(minutes):02}:{seconds_val:06.3f}"

def hhmmss_to_seconds(time_str: str) -> float:
    parts = time_str.split(':')
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

def format_output_filename(template: str, data: dict) -> str:
    try:
        return template.format(**data)
    except KeyError as e:
        raise ValueError(f"Invalid placeholder '{{{e.args[0]}}}' in output template.")

def generate_ffmpeg_mapping_args(all_streams: list[dict], selected_track_ids: list[int], lang_priority: list[str]) -> list[str]:
    args = []
    
    video_streams = [t for t in all_streams if t.get('codec_type') == 'video']
    for track in video_streams: args.extend(["-map", f"0:{track['index']}"])

    audio_tracks = [t for t in all_streams if t.get('codec_type') == 'audio' and t.get('id') in selected_track_ids]
    subtitle_tracks = [t for t in all_streams if t.get('codec_type') == 'subtitle' and t.get('id') in selected_track_ids]

    def sort_key(track):
        try:
            lang = track.get('tags', {}).get('language', 'und').lower()
            return lang_priority.index(lang), int(track.get('id'))
        except (ValueError, TypeError):
            return len(lang_priority), int(track.get('id'))

    audio_tracks.sort(key=sort_key)
    subtitle_tracks.sort(key=sort_key)
    
    if audio_tracks:
        for i, track in enumerate(audio_tracks):
            args.extend(["-map", f"0:{track['index']}"])
            disposition = "default" if i == 0 else "0"
            args.extend([f"-disposition:a:{i}", disposition])
    else: args.append("-an")

    if subtitle_tracks:
        for i, track in enumerate(subtitle_tracks):
            args.extend(["-map", f"0:{track['index']}"])
            disposition = "default" if i == 0 else "0"
            args.extend([f"-disposition:s:{i}", disposition])
    else: args.append("-sn")

    return args

def trim_video_segment(
    input_video: Path, output_video: Path, start_sec: float, end_sec: float,
    video_mode: str, crop_filter: str | None, mapping_args: list[str], worker=None
):
    duration = end_sec - start_sec
    
    if video_mode == 'smart-cut':
        command = [resolve_tool("smartcut"), str(input_video), str(output_video), "--keep", f"{start_sec},{end_sec}"]
        try:
            process = subprocess.run(command, check=True, text=True, capture_output=True, encoding='utf-8',
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if worker: worker.progress_updated.emit(100)
            return
        except FileNotFoundError:
            raise FileNotFoundError("`smartcut` command not found. Is it installed and in your system's PATH?")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Error during smartcut for {output_video.name}:\n{e.stderr}")

    if video_mode == 'copy': codecs = ["-c", "copy"]
    elif video_mode == 're-encode': codecs = ["-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-c:s", "copy"]
    elif video_mode == 'ffv1': codecs = ["-c:v", "ffv1", "-level", "3", "-g", "1", "-c:a", "copy", "-c:s", "copy"]
    else: codecs = []
    
    filter_cmd = ["-vf", crop_filter] if crop_filter else []

    command = [
        resolve_tool("ffmpeg"), "-y", "-ss", convert_seconds_to_hhmmss(start_sec),
        "-to", convert_seconds_to_hhmmss(end_sec), "-i", str(input_video),
        *filter_cmd, *mapping_args, *codecs, str(output_video)
    ]
    
    process = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               universal_newlines=True, encoding="utf-8",
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    for line in process.stderr:
        if worker and worker._is_cancelled:
            process.terminate(); return
        match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", line)
        if match and worker and video_mode != 'copy':
            elapsed_time = hhmmss_to_seconds(match.group(1))
            percentage = int((elapsed_time / duration) * 100)
            worker.progress_updated.emit(min(100, percentage))
    
    process.wait()
    if process.returncode != 0: raise RuntimeError(f"FFmpeg failed for segment {output_video.name}.")

def merge_videos(clip_paths: list[Path], final_output: Path, worker=None):
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".txt", encoding='utf-8') as manifest:
        for clip_path in clip_paths: manifest.write(f"file '{clip_path.resolve().as_posix()}'\n")
        manifest_path = manifest.name
    command = [resolve_tool("ffmpeg"), "-f", "concat", "-safe", "0", "-i", manifest_path, "-c", "copy", "-y", str(final_output), "-loglevel", "error"]
    try: subprocess.run(command, check=True, text=True, stderr=subprocess.PIPE, encoding='utf-8',
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.CalledProcessError as e: raise RuntimeError(f"Error during final merge:\n{e.stderr}")
    finally: Path(manifest_path).unlink()

def run_powertrim_job(settings: dict, worker=None):
    input_video, mode, segments_raw = settings["input_video"], settings["mode"], settings["segments_raw"]
    output_template, merge, video_mode = settings["output_template"], settings["merge"], settings["video_mode"]
    autocrop = settings.get("autocrop", False)
    lang_priority = settings.get("lang_priority", [])
    selected_track_ids = settings.get("selected_track_ids", [])
    output_dir = settings.get("output_dir"); output_file = settings.get("output_file")

    if not segments_raw: raise ValueError("No valid segments found to process.")
    video_meta = get_video_metadata(input_video)
    if not video_meta: raise ValueError("Could not retrieve video metadata.")
    
    frame_rate = video_meta.get('fps', 0)
    if mode == "frames" and frame_rate == 0: raise ValueError("Frame mode selected, but could not determine frame rate.")

    segments_in_seconds = [(s[0] / frame_rate, s[1] / frame_rate) for s in segments_raw] if mode == 'frames' else segments_raw
    crop_params = detect_black_bars(input_video, video_meta.get('duration', 0), worker) if autocrop else None

    all_streams = video_meta.get("streams", [])
    mapping_args = generate_ffmpeg_mapping_args(all_streams, selected_track_ids, lang_priority)
    
    now = datetime.now()
    base_template_data = {"filename": sanitize_filename(input_video.stem), "resolution": video_meta.get('resolution', 'unknown'),
                          "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H-%M-%S")}

    video_extension = ".mkv" if video_mode == 'ffv1' else ".mp4" if 're-encode' in video_mode else input_video.suffix

    if merge:
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir, temp_clip_paths = Path(temp_dir_str), []
            total = len(segments_in_seconds)
            for i, (start, end) in enumerate(segments_in_seconds):
                if worker and worker._is_cancelled: return "Cancelled"
                ### MODIFIED: Emit more detailed status ###
                if worker:
                    worker.clip_started.emit(i + 1, total)
                    worker.step_changed.emit(f"Processing clip {i+1} of {total}...")
                
                clip_path = temp_dir / f"temp_{i+1:03d}{video_extension}"
                trim_video_segment(input_video, clip_path, start, end, video_mode, crop_params, mapping_args, worker)
                temp_clip_paths.append(clip_path)

            if worker and worker._is_cancelled: return "Cancelled"
            if worker: worker.step_changed.emit("Merging all clips...")
            final_path = Path(output_file)
            merge_videos(temp_clip_paths, final_path, worker)
            return str(final_path.resolve())
    else:
        total = len(segments_in_seconds)
        for i, (start, end) in enumerate(segments_in_seconds):
            if worker and worker._is_cancelled: return "Cancelled"
            
            seg_data = base_template_data | {"num": i + 1, "start": int(segments_raw[i][0]), "end": int(segments_raw[i][1])}
            output_name = format_output_filename(output_template, seg_data)
            output_path = Path(output_dir) / f"{output_name}{video_extension}"
            
            ### MODIFIED: Emit more detailed status ###
            if worker:
                worker.clip_started.emit(i + 1, total)
                worker.step_changed.emit(f"Exporting clip {i+1} of {total}: {output_path.name}")
            
            trim_video_segment(input_video, output_path, start, end, video_mode, crop_params, mapping_args, worker)
        return str(Path(output_dir).resolve())