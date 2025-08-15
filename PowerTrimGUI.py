#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
A professional, all-in-one video trimming and segment management application
using PySide6 and python-mpv, inspired by modern video editors like LosslessCut.
"""

import sys
import os
import csv
import json
import subprocess
import hashlib
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QDockWidget, QListWidget, QListWidgetItem,
    QMessageBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsPixmapItem, QToolBar, QSlider, QGraphicsLineItem, QProgressDialog,
    QToolButton, QMenu, QFormLayout, QLineEdit, QGraphicsPolygonItem, QGroupBox,
    QFrame, QStyle, QAbstractItemView, QDialog, QDialogButtonBox, QRadioButton,
    QCheckBox, QTabWidget, QComboBox, QButtonGroup, QProgressBar, QColorDialog,
    QSpinBox
)
from PySide6.QtGui import (
    QColor, QPen, QBrush, QKeySequence, QShortcut, QFont,
    QPixmap, QImage, QAction, QIcon, QActionGroup, QPolygonF, QCursor
)
from PySide6.QtCore import Qt, Signal, QObject, QThread, QTimer, QPointF, QSize, Slot, QSettings, QTime

import mpv
from icons import create_icon_from_svg, ICON_DATA
# Import the backend engine
from powertrim_engine import run_powertrim_job, sanitize_filename, get_video_metadata, resolve_tool

# --- Modern Dark Stylesheet ---
DARK_STYLESHEET = """
QWidget{background-color:#2e2e2e;color:#e0e0e0;font-family:'Segoe UI',Arial,sans-serif;font-size:10pt}QMainWindow{background-color:#1e1e1e}QDockWidget{background-color:#2a2a2a}QDockWidget::title{background-color:#383838;text-align:left;padding:5px;border:1px solid #1e1e1e;cursor:openhand;}QToolBar{background-color:#333333;border:none;padding:2px}QToolBar QToolButton{padding:6px;border:1px solid #3c3c3c;border-radius:3px}QToolBar QToolButton:hover{background-color:#4a4a4a}QToolBar QToolButton:disabled{color:#787878}QToolBar QToolButton::menu-indicator{image:none}QPushButton{background-color:#4a4a4a;border:1px solid #5a5a5a;padding:5px;min-width:40px;border-radius:3px}QPushButton:hover{background-color:#5a5a5a}QPushButton:pressed{background-color:#6a6a6a}QPushButton:disabled{background-color:#404040;color:#787878}QListWidget{background-color:#282828;border:1px solid #3c3c3c;border-radius:3px}QGraphicsView{border:none;background-color:#222222}QStatusBar{background-color:#1e1e1e;border-top:1px solid #3c3c3c}QMessageBox{background-color:#2e2e2e}QSlider::groove:horizontal{border:1px solid #4a4a4a;height:4px;background:#3e3e3e;margin:2px 0;border-radius:2px}QSlider::handle:horizontal{background:#c0c0c0;border:1px solid #a0a0a0;width:14px;margin:-6px 0;border-radius:7px}QMenu{background-color:#2e2e2e;border:1px solid #4a4a4a}QMenu::item:selected{background-color:#4a4a4a}QLineEdit,QSpinBox{border:1px solid #5a5a5a;border-radius:3px;padding:2px}QLineEdit:read-only,QSpinBox:read-only{background-color:#3a3a3a}QFrame[frameShape="5"]{border:1px solid #4a4a4a}
QTabWidget::pane{border:1px solid #3c3c3c;border-radius:3px}QTabBar::tab{background-color:#2e2e2e;padding:5px 10px;border-top-left-radius:3px;border-top-right-radius:3px}QTabBar::tab:selected{background-color:#4a4a4a}QTabBar::tab:!selected{background-color:#383838}
QProgressBar{border:1px solid #5a5a5a;border-radius:3px;text-align:center;background-color:#282828}QProgressBar::chunk{background-color:#4a8cc2;border-radius:3px}
"""

def _app_root():
    if getattr(sys, 'frozen', False):
        # For PyInstaller builds, check if we're in the _internal structure
        exe_dir = Path(sys.executable).resolve().parent
        internal_bin = exe_dir / '_internal' / 'bin'
        if internal_bin.exists():
            return exe_dir / '_internal'
        return exe_dir
    return Path(__file__).resolve().parent

def _is_portable_mode() -> bool:
    try:
        if os.getenv('POWERTRIM_PORTABLE', '0') == '1':
            return True
        return (_app_root() / 'portable_mode').exists()
    except Exception:
        return False

def _portable_bin_bootstrap():
    if os.name == 'nt':
        bin_dir = _app_root() / 'bin'
        try:
            if bin_dir.exists():
                os.environ['PATH'] = str(bin_dir) + os.pathsep + os.environ.get('PATH', '')
                try:
                    os.add_dll_directory(str(bin_dir))
                except Exception:
                    pass
        except Exception:
            pass

_portable_bin_bootstrap()

def get_app_settings() -> QSettings:
    if _is_portable_mode():
        ini_path = _app_root() / 'PowerTrim.ini'
        return QSettings(str(ini_path), QSettings.IniFormat)
    return QSettings("PowerTrim", "PowerTrimGUI")

def _default_output_dir() -> str:
    return str((_app_root() / 'output').resolve())

def _default_snapshot_dir() -> str:
    return str((_app_root() / 'snapshots').resolve())

def _ensure_portable_dirs_and_defaults(settings: QSettings) -> None:
    if not _is_portable_mode():
        return
    # Create default directories
    try:
        Path(_default_output_dir()).mkdir(parents=True, exist_ok=True)
        Path(_default_snapshot_dir()).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # Seed defaults if unset
    try:
        if not settings.value("export/defaultDirectory", "", str):
            settings.setValue("export/defaultDirectory", _default_output_dir())
        if not settings.value("snapshot/quickSavePath", "", str):
            settings.setValue("snapshot/quickSavePath", _default_snapshot_dir())
    except Exception:
        pass

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(550)
        self.settings = get_app_settings()
        
        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        self.create_export_tab()
        self.create_snapshot_tab()
        self.create_playback_tab()
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.save_settings)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)
        
        self.load_settings()

    def create_export_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        
        self.export_dir_edit = QLineEdit()
        browse_export_btn = QPushButton("Browse...")
        browse_export_btn.clicked.connect(lambda: self.browse_directory(self.export_dir_edit, "Select Default Export Directory"))
        export_dir_layout = QHBoxLayout(); export_dir_layout.addWidget(self.export_dir_edit); export_dir_layout.addWidget(browse_export_btn)
        layout.addRow("Default Output Directory:", export_dir_layout)
        
        self.export_mode_group = QGroupBox("Default Export Mode")
        mode_layout = QVBoxLayout()
        self.rb_export_copy = QRadioButton("Lossless Copy"); self.rb_export_smart = QRadioButton("Smart Cut")
        self.rb_export_reencode = QRadioButton("Re-encode"); self.rb_export_ffv1 = QRadioButton("Archival (FFV1)")
        self.export_mode_btn_group = QButtonGroup()
        for rb in [self.rb_export_copy, self.rb_export_smart, self.rb_export_reencode, self.rb_export_ffv1]:
            mode_layout.addWidget(rb); self.export_mode_btn_group.addButton(rb)
        self.export_mode_group.setLayout(mode_layout)
        layout.addRow(self.export_mode_group)
        
        self.lang_priority_edit = QLineEdit()
        layout.addRow("Default Language Priority:", self.lang_priority_edit)
        
        self.tabs.addTab(tab, "Export")

    def create_snapshot_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        self.snapshot_dir_edit = QLineEdit()
        browse_snapshot_btn = QPushButton("Browse...")
        browse_snapshot_btn.clicked.connect(lambda: self.browse_directory(self.snapshot_dir_edit, "Select Quick Snapshot Directory"))
        snapshot_dir_layout = QHBoxLayout(); snapshot_dir_layout.addWidget(self.snapshot_dir_edit); snapshot_dir_layout.addWidget(browse_snapshot_btn)
        layout.addRow("Quick Snapshot Directory:", snapshot_dir_layout)

        self.snapshot_format_combo = QComboBox()
        self.snapshot_format_combo.addItems(["PNG", "JPEG"])
        layout.addRow("Quick Snapshot Format:", self.snapshot_format_combo)

        self.snapshot_template_edit = QLineEdit()
        template_label = QLabel("Filename Template:<br><small><i>Placeholders: {filename}, {frame_num}, {time_ms}</i></small>")
        layout.addRow(template_label, self.snapshot_template_edit)

        self.tabs.addTab(tab, "Snapshots")

    def create_playback_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)
        self.scrub_on_hover_checkbox = QCheckBox("Enable Timeline Scrubbing on Hover")
        self.scrub_on_hover_checkbox.setToolTip("When paused, shows the video frame under the mouse cursor on the timeline.")
        layout.addRow(self.scrub_on_hover_checkbox)
        self.tabs.addTab(tab, "Playback")

    def browse_directory(self, line_edit, title):
        directory = QFileDialog.getExistingDirectory(self, title, line_edit.text())
        if directory:
            line_edit.setText(directory)

    def load_settings(self):
        default_export_dir = _default_output_dir() if _is_portable_mode() else ""
        self.export_dir_edit.setText(self.settings.value("export/defaultDirectory", default_export_dir, str))
        self.lang_priority_edit.setText(self.settings.value("export/languagePriority", "eng,jpn", str))
        default_mode = self.settings.value("export/defaultMode", "Lossless Copy", str)
        for rb in self.export_mode_btn_group.buttons():
            if rb.text() == default_mode:
                rb.setChecked(True); break
        default_snap_dir = _default_snapshot_dir() if _is_portable_mode() else ""
        self.snapshot_dir_edit.setText(self.settings.value("snapshot/quickSavePath", default_snap_dir, str))
        self.snapshot_format_combo.setCurrentText(self.settings.value("snapshot/format", "PNG", str))
        self.snapshot_template_edit.setText(self.settings.value("snapshot/template", "{filename}_frame_{frame_num}", str))
        self.scrub_on_hover_checkbox.setChecked(self.settings.value("playback/hoverScrub", True, bool))

    def save_settings(self):
        self.settings.setValue("export/defaultDirectory", self.export_dir_edit.text())
        self.settings.setValue("export/languagePriority", self.lang_priority_edit.text())
        if self.export_mode_btn_group.checkedButton():
            self.settings.setValue("export/defaultMode", self.export_mode_btn_group.checkedButton().text())
        self.settings.setValue("snapshot/quickSavePath", self.snapshot_dir_edit.text())
        self.settings.setValue("snapshot/format", self.snapshot_format_combo.currentText())
        self.settings.setValue("snapshot/template", self.snapshot_template_edit.text())
        self.settings.setValue("playback/hoverScrub", self.scrub_on_hover_checkbox.isChecked())
        self.accept()

# --- Data Models and Core Logic ---
class Segment:
    def __init__(self, start_frame, end_frame, color, name=""):
        self.start_frame, self.end_frame, self.color, self.name = start_frame, end_frame, color, name or f"Segment [{start_frame}-{end_frame}]"

class SegmentManager(QObject):
    model_changed = Signal()
    def __init__(self):
        super().__init__()
        self.segments, self.fps = [], 0
    def add_segment(self, data, index=-1):
        segment = Segment(data[0], data[1], data[2], name=data[3] if len(data) > 3 else "")
        if index == -1: self.segments.append(segment)
        else: self.segments.insert(index, segment)
        self.model_changed.emit()
    def remove_segment(self, index):
        if 0 <= index < len(self.segments):
            del self.segments[index]; self.model_changed.emit()
    def update_segment(self, index, data):
        if 0 <= index < len(self.segments):
            self.segments[index] = Segment(data[0], data[1], data[2], name=data[3] if len(data) > 3 else ""); self.model_changed.emit()
    def set_segments(self, segments_data):
        self.segments = [Segment(d[0], d[1], d[2], name=d[3]) for d in segments_data]; self.model_changed.emit()
    def get_all_segments(self): return self.segments

# --- Command Pattern for Undo/Redo ---
class Command:
    def execute(self): raise NotImplementedError
    def undo(self): raise NotImplementedError
class AddSegmentCommand(Command):
    def __init__(self, sm, data): self.sm, self.data = sm, data
    def execute(self): self.sm.add_segment(self.data)
    def undo(self): self.sm.remove_segment(len(self.sm.segments) - 1)
class DeleteSegmentCommand(Command):
    def __init__(self, sm, index, data): self.sm, self.index, self.data = sm, index, data
    def execute(self): self.sm.remove_segment(self.index)
    def undo(self): self.sm.add_segment(self.data, self.index)
class UpdateSegmentCommand(Command):
    def __init__(self, sm, index, old, new): self.sm, self.index, self.old, self.new = sm, index, old, new
    def execute(self): self.sm.update_segment(self.index, self.new)
    def undo(self): self.sm.update_segment(self.index, self.old)
class ImportSegmentsCommand(Command):
    def __init__(self, sm, old, new): self.sm, self.old, self.new = sm, old, new
    def execute(self): self.sm.set_segments(self.new)
    def undo(self): self.sm.set_segments(self.old)
class MergeSegmentsCommand(Command):
    def __init__(self, sm, indices, merged_data):
        self.sm, self.indices, self.merged_data = sm, sorted(indices, reverse=True), merged_data
        self.original_data, self.insert_index = [], -1
    def execute(self):
        if not self.original_data:
            all_segs = self.sm.get_all_segments()
            for index in sorted(self.indices, reverse=False):
                seg = all_segs[index]; self.original_data.append((seg.start_frame, seg.end_frame, seg.color, seg.name))
        for index in self.indices: self.sm.remove_segment(index)
        self.insert_index = self.indices[-1]; self.sm.add_segment(self.merged_data, index=self.insert_index)
    def undo(self):
        self.sm.remove_segment(self.insert_index)
        for i, index in enumerate(sorted(self.indices, reverse=False)): self.sm.add_segment(self.original_data[i], index=index)
class UndoManager(QObject):
    undo_stack_changed = Signal(bool)
    redo_stack_changed = Signal(bool)
    command_executed = Signal() ### NEW SIGNAL for dirty state
    def __init__(self): super().__init__(); self.undo_stack, self.redo_stack = [], []
    def execute(self, cmd): 
        cmd.execute(); self.undo_stack.append(cmd); self.redo_stack.clear(); self.update_stack_states()
        self.command_executed.emit()
    def undo(self):
        if self.undo_stack: cmd = self.undo_stack.pop(); cmd.undo(); self.redo_stack.append(cmd); self.update_stack_states()
        self.command_executed.emit()
    def redo(self):
        if self.redo_stack: cmd = self.redo_stack.pop(); cmd.execute(); self.undo_stack.append(cmd); self.update_stack_states()
        self.command_executed.emit()
    def update_stack_states(self): self.undo_stack_changed.emit(len(self.undo_stack) > 0); self.redo_stack_changed.emit(len(self.redo_stack) > 0)
    def clear(self): self.undo_stack.clear(); self.redo_stack.clear(); self.update_stack_states()

# --- Worker Objects ---
class ThumbnailLoader(QObject):
    thumbnail_ready = Signal(int, QImage); finished = Signal()
    def __init__(self, video_path, duration, num_thumbnails):
        super().__init__(); self.video_path, self.duration, self.num_thumbnails = video_path, duration, num_thumbnails; self._is_running = True
    def run(self):
        try:
            video_file = Path(self.video_path)
            cache_root = video_file.parent / ".powertrim_cache" / "thumbs"
            cache_root.mkdir(parents=True, exist_ok=True)
            # Include path + mtime + count to refresh cache when source changes or layout differs
            cache_key = hashlib.sha1((str(video_file.resolve()) + f"|{video_file.stat().st_mtime_ns}|{self.num_thumbnails}").encode('utf-8')).hexdigest()[:16]
            cache_dir = cache_root / cache_key
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Collect existing thumbs
            existing = sorted([p for p in cache_dir.glob('thumb_*.jpg')])
            if len(existing) < self.num_thumbnails:
                # Generate uniformly spaced thumbnails in one ffmpeg run; pre-scale to height 70
                fps_val = max(1e-6, self.num_thumbnails / max(1e-6, float(self.duration)))
                out_pattern = (cache_dir / 'thumb_%03d.jpg').as_posix()
                cmd = [
                    'ffmpeg', '-y', '-i', self.video_path,
                    '-vf', f"fps={fps_val},scale=-1:70",
                    '-q:v', '5', out_pattern
                ]
                try:
                    subprocess.run(
                        cmd,
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass
                existing = sorted([p for p in cache_dir.glob('thumb_*.jpg')])

            # Emit up to num_thumbnails
            for idx, img_path in enumerate(existing[:self.num_thumbnails]):
                if not self._is_running:
                    break
                img = QImage(str(img_path))
                if not img.isNull():
                    self.thumbnail_ready.emit(idx, img)
        finally:
            self.finished.emit()
    def stop(self): self._is_running = False

class ExportWorker(QObject):
    clip_started = Signal(int, int)
    step_changed = Signal(str)
    progress_updated = Signal(int)
    finished = Signal(str)
    error = Signal(str)
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._is_cancelled = False
    def run(self):
        try:
            result_path = run_powertrim_job(self.settings, self)
            if not self._is_cancelled:
                self.finished.emit(result_path)
        except Exception as e:
            self.error.emit(str(e))
    @Slot()
    def stop(self): self._is_cancelled = True

class MpvSignalBridge(QObject):
    time_pos_changed = Signal(float); duration_changed = Signal(float); paused_changed = Signal(bool)
    container_fps_changed = Signal(float); track_list_changed = Signal(list); volume_changed = Signal(float); mute_changed = Signal(bool)

class ExportStatusDialog(QDialog):
    cancelled = Signal()

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Exporting Video")
        self.setMinimumWidth(450)
        self.settings = settings or {}

        layout = QVBoxLayout(self)

        self.overall_label = QLabel("Overall Progress")
        self.overall_progress = QProgressBar()
        layout.addWidget(self.overall_label)
        layout.addWidget(self.overall_progress)

        self.current_clip_label = QLabel("Starting...")
        self.current_clip_progress = QProgressBar()
        layout.addWidget(self.current_clip_label)
        layout.addWidget(self.current_clip_progress)
        
        details_group = QGroupBox("Details")
        details_layout = QFormLayout(details_group)
        self.mode_label = QLabel(self.settings.get("video_mode", "N/A").replace("-", " ").title())
        self.time_elapsed_label = QLabel("00:00:00")
        details_layout.addRow("Mode:", self.mode_label)
        details_layout.addRow("Time Elapsed:", self.time_elapsed_label)
        layout.addWidget(details_group)

        self.open_folder_checkbox = QCheckBox("Open output folder when finished")
        self.open_folder_checkbox.setChecked(True)
        layout.addWidget(self.open_folder_checkbox)
        
        self.button_box = QDialogButtonBox()
        self.cancel_button = self.button_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        layout.addWidget(self.button_box)
        
        self.cancel_button.clicked.connect(self.cancelled.emit)
        
        self.time = QTime(0,0,0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)

    def start_timer(self):
        self.timer.start(1000)

    def update_timer(self):
        self.time = self.time.addSecs(1)
        self.time_elapsed_label.setText(self.time.toString("hh:mm:ss"))

    @Slot(int, int)
    def update_overall_progress(self, current, total):
        self.overall_progress.setRange(0, total)
        self.overall_progress.setValue(current)
        self.overall_label.setText(f"Overall Progress (Clip {current} of {total})")
        
        self.current_clip_progress.setValue(0)
        if self.settings.get("video_mode") in ["copy", "smart-cut"]:
            self.current_clip_progress.setRange(0, 0) 
        else:
            self.current_clip_progress.setRange(0, 100)

    @Slot(str)
    def update_step_text(self, text):
        self.current_clip_label.setText(text)

    @Slot(int)
    def update_current_progress(self, value):
        if self.current_clip_progress.minimum() == 0 and self.current_clip_progress.maximum() == 0:
            return
        self.current_clip_progress.setValue(value)

    def closeEvent(self, event):
        self.cancelled.emit()
        super().closeEvent(event)

class TrackSelectionWidget(QWidget):
    # ... (This class is unchanged) ...
    def __init__(self, tracks, title):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        group = QGroupBox(title)
        self.layout().addWidget(group)
        
        self.track_layout = QVBoxLayout()
        group.setLayout(self.track_layout)
        
        self.checkboxes = []
        for track in tracks:
            track_id = track.get('id')
            lang = track.get('tags', {}).get('language', 'und')
            title_text = track.get('tags', {}).get('title', f"Track {track_id}")
            codec = track.get('codec_name', 'unknown')
            
            cb = QCheckBox(f"#{track_id}: {title_text} [{lang}] ({codec})")
            cb.setChecked(True)
            cb.setProperty("track_id", track_id)
            self.checkboxes.append(cb)
            self.track_layout.addWidget(cb)
            
    def get_selected_track_ids(self):
        return [cb.property("track_id") for cb in self.checkboxes if cb.isChecked()]

class ExportDialog(QDialog):
    # ... (This class is unchanged) ...
    def __init__(self, parent, default_filename, all_tracks, video_metadata, settings):
        super().__init__(parent)
        self.setWindowTitle("Export Video")
        self.setMinimumWidth(500)
        self.default_filename = sanitize_filename(default_filename)
        self.video_metadata = video_metadata
        self.settings = settings
        layout = QVBoxLayout(self)

        video_group = QGroupBox("Video Mode")
        video_layout = QVBoxLayout()
        self.rb_copy = QRadioButton("Lossless Copy (Fast, Remux Only)");
        self.rb_smart = QRadioButton("Smart Cut (Frame-Accurate, Audio Copied)")
        self.rb_reencode = QRadioButton("Re-encode (H.264/AAC, Allows Cropping)")
        self.rb_ffv1 = QRadioButton("Archival (FFV1 Lossless/Copy Audio)")
        video_layout.addWidget(self.rb_copy); video_layout.addWidget(self.rb_smart)
        video_layout.addWidget(self.rb_reencode); video_layout.addWidget(self.rb_ffv1)
        video_group.setLayout(video_layout)
        layout.addWidget(video_group)
        
        default_mode = self.settings.value("export/defaultMode", "Lossless Copy", str)
        if default_mode == "Smart Cut": self.rb_smart.setChecked(True)
        elif default_mode == "Re-encode": self.rb_reencode.setChecked(True)
        elif default_mode == "Archival (FFV1)": self.rb_ffv1.setChecked(True)
        else: self.rb_copy.setChecked(True)

        track_group = QGroupBox("Track & Language Settings")
        track_form_layout = QFormLayout()
        
        self.le_lang_priority = QLineEdit(self.settings.value("export/languagePriority", "eng,jpn", str))
        self.le_lang_priority.setToolTip("Comma-separated list of preferred languages (e.g., eng,jpn,ger). The first match becomes default.")
        track_form_layout.addRow("Language Priority:", self.le_lang_priority)
        
        audio_tracks = [t for t in all_tracks if t.get('codec_type') == 'audio']
        subtitle_tracks = [t for t in all_tracks if t.get('codec_type') == 'subtitle']
        
        self.audio_selector = TrackSelectionWidget(audio_tracks, "Include Audio Tracks")
        self.subtitle_selector = TrackSelectionWidget(subtitle_tracks, "Include Subtitle Tracks")
        
        if audio_tracks: track_form_layout.addRow(self.audio_selector)
        if subtitle_tracks: track_form_layout.addRow(self.subtitle_selector)
        
        track_group.setLayout(track_form_layout)
        layout.addWidget(track_group)
        
        options_group = QGroupBox("Options")
        options_layout = QFormLayout()
        self.cb_merge = QCheckBox("Merge all segments into a single file"); self.cb_merge.setChecked(True)
        self.cb_autocrop = QCheckBox("Auto-crop black bars")
        options_layout.addRow(self.cb_merge); options_layout.addRow(self.cb_autocrop)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        output_group = QGroupBox("Output Filename Template")
        output_layout = QFormLayout()
        self.le_output_name = QLineEdit()
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet("color: #a0a0a0; font-style: italic;")
        output_layout.addRow("Template:", self.le_output_name)
        output_layout.addRow("Preview:", self.lbl_preview)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        for rb in [self.rb_reencode, self.rb_ffv1, self.cb_merge]:
            rb.toggled.connect(self._update_ui_state)
        self.le_output_name.textChanged.connect(self._update_ui_state)
        
        self._check_codec_compatibility()
        self._update_ui_state()

    def _check_codec_compatibility(self):
        if not self.video_metadata: return
        video_stream = next((s for s in self.video_metadata.get("streams", []) if s.get("codec_type") == "video"), None)
        if not video_stream: return

        codec_name = video_stream.get('codec_name', '').lower()
        profile = video_stream.get('profile', '')

        if codec_name == 'vp9' and profile in ['Profile 2', 'Profile 3']:
            self.rb_smart.setEnabled(False)
            self.rb_smart.setToolTip("Smart Cut is not supported for this video's codec (VP9 HDR).\nPlease choose 'Re-encode' for a frame-accurate cut.")
            if self.rb_smart.isChecked(): self.rb_reencode.setChecked(True)

    def _update_ui_state(self):
        is_reencode = self.rb_reencode.isChecked() or self.rb_ffv1.isChecked()
        self.cb_autocrop.setEnabled(is_reencode)
        if not is_reencode:
            self.cb_autocrop.setChecked(False)
            self.cb_autocrop.setToolTip("Auto-cropping requires a re-encode mode.")
        else: self.cb_autocrop.setToolTip("")
        
        current_text = self.le_output_name.text()
        default_merged = "{filename}_merged"; default_separate = "{filename}_segment_{num:03d}"
        if current_text in ["", default_merged, default_separate]:
            template = default_merged if self.cb_merge.isChecked() else default_separate
            self.le_output_name.setText(template)
        else: template = current_text

        preview = template.replace("{filename}", self.default_filename).replace("{num:03d}", "001").replace("{num}", "1")
        ext = ".mkv" if self.rb_ffv1.isChecked() else ".mp4"
        self.lbl_preview.setText(f"{preview}{ext}")

    def get_settings(self):
        video_mode = 'copy'
        if self.rb_smart.isChecked(): video_mode = 'smart-cut'
        elif self.rb_reencode.isChecked(): video_mode = 're-encode'
        elif self.rb_ffv1.isChecked(): video_mode = 'ffv1'
        return {"video_mode": video_mode, "merge": self.cb_merge.isChecked(), "autocrop": self.cb_autocrop.isChecked(), "output_template": self.le_output_name.text()}

    def get_track_settings(self):
        selected_ids = self.audio_selector.get_selected_track_ids() + self.subtitle_selector.get_selected_track_ids()
        return {"lang_priority": [lang.strip().lower() for lang in self.le_lang_priority.text().split(',')], "selected_track_ids": selected_ids}

# --- Main Application Window (Controller) ---
class ProTrimmerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = get_app_settings()
        _ensure_portable_dirs_and_defaults(self.settings)
        self.setWindowTitle("PowerTrim"); self.setGeometry(100, 100, 1600, 900); self.setStyleSheet(DARK_STYLESHEET)
        self.setAcceptDrops(True)
        self.video_path, self.duration, self.fps, self.total_frames, self.current_frame = None, 0, 0, 0, 0
        self.in_point, self.out_point = -1, -1
        self.playhead = None
        self.thumb_loader_thread = None
        self.thumb_loader_worker = None
        self.mpv_signals = MpvSignalBridge(); self.undo_manager = UndoManager()
        # Professional video editing color palette - 16 vibrant colors with good contrast
        self.segment_colors = [
            QColor(255, 87, 87, 120),    # Vibrant Red
            QColor(87, 187, 255, 120),   # Bright Blue
            QColor(87, 255, 159, 120),   # Electric Green
            QColor(255, 255, 87, 120),   # Bright Yellow
            QColor(187, 87, 255, 120),   # Vibrant Purple
            QColor(255, 167, 87, 120),   # Bright Orange
            QColor(255, 87, 255, 120),   # Magenta
            QColor(87, 255, 255, 120),   # Cyan
            QColor(255, 187, 87, 120),   # Golden Yellow
            QColor(87, 255, 87, 120),    # Lime Green
            QColor(255, 87, 187, 120),   # Pink
            QColor(187, 255, 87, 120),   # Light Green
            QColor(87, 187, 187, 120),   # Teal
            QColor(187, 187, 255, 120),  # Light Blue
            QColor(255, 187, 255, 120),  # Light Magenta
            QColor(187, 255, 187, 120)   # Mint Green
        ]
        self._color_idx = 0
        self._is_scrolling_programmatically = False
        self.is_playing_segment = False; self.segment_playback_end = -1
        self.pending_project_segments = None
        self.last_volume = 70
        self.thumbs_loading_text_item = None
        self.export_thread = None
        self.export_worker = None
        self.export_dialog = None
        self.is_project_dirty = False
        self.icons = {name: create_icon_from_svg(svg, "white") for name, svg in ICON_DATA.items()}
        self.setup_ui()
        self.setup_player()
        self.setup_connections()
        self.set_player_controls_enabled(False)
        self.actions['mark_out'].setEnabled(False)

    def setup_ui(self):
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget); main_layout.setContentsMargins(5,5,5,5); main_layout.setSpacing(5)
        self.video_container = QWidget(); self.video_container.setStyleSheet("background-color: black;"); main_layout.addWidget(self.video_container, stretch=1)
        timeline_section = QWidget(); timeline_layout = QVBoxLayout(timeline_section); timeline_layout.setSpacing(0)
        self.timeline = QGraphicsView(); self.timeline.setFixedHeight(60); self.timeline_scene = QGraphicsScene(); self.timeline.setScene(self.timeline_scene)
        self.thumbnails = QGraphicsView(); self.thumbnails.setFixedHeight(80); self.thumbnails_scene = QGraphicsScene(); self.thumbnails.setScene(self.thumbnails_scene)
        for view in [self.timeline, self.thumbnails]:
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn); view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            view.setMouseTracking(True); view.viewport().setCursor(Qt.PointingHandCursor)
        timeline_layout.addWidget(self.timeline); timeline_layout.addWidget(self.thumbnails); main_layout.addWidget(timeline_section)
        
        controls_panel = QWidget(); controls_layout = QHBoxLayout(controls_panel); controls_layout.setAlignment(Qt.AlignCenter)
        
        self.connections = {}
        button_defs = {'jump_start': {'icon': self.icons['skip-back-line']},'prev_boundary': {'icon': self.icons['skip-left-line']},'prev_frame': {'icon': self.icons['arrow-left-s-line']},'play_pause': {'icon': self.icons['play-line']},'next_frame': {'icon': self.icons['arrow-right-s-line']},'next_boundary': {'icon': self.icons['skip-right-line']},'jump_end': {'icon': self.icons['skip-forward-line']}}
        for name, props in button_defs.items():
            btn = QPushButton(""); btn.setIcon(props['icon']); btn.setFixedSize(QSize(50, 30))
            if name == 'play_pause': btn.setFixedSize(QSize(100, 30))
            self.connections[name] = btn

        nav_group, center_group, end_nav_group = ['jump_start', 'prev_boundary', 'prev_frame'], ['play_pause'], ['next_frame', 'next_boundary', 'jump_end']
        controls_layout.addStretch(2)
        for btn_name in nav_group: controls_layout.addWidget(self.connections[btn_name])
        controls_layout.addWidget(self.create_separator())
        for btn_name in center_group: controls_layout.addWidget(self.connections[btn_name])
        controls_layout.addWidget(self.create_separator())
        for btn_name in end_nav_group: controls_layout.addWidget(self.connections[btn_name])
        controls_layout.addStretch(1)

        zoom_layout = QHBoxLayout(); zoom_layout.addWidget(QLabel("Zoom:"))
        self.zoom_out_btn = QPushButton(""); self.zoom_out_btn.setIcon(self.icons['zoom-out-line']); self.zoom_out_btn.setFixedSize(35, 30)
        zoom_layout.addWidget(self.zoom_out_btn)
        self.zoom_slider = QSlider(Qt.Horizontal); self.zoom_slider.setRange(100, 1000); self.zoom_slider.setValue(100); self.zoom_slider.setFixedWidth(150); zoom_layout.addWidget(self.zoom_slider)
        self.zoom_in_btn = QPushButton(""); self.zoom_in_btn.setIcon(self.icons['zoom-in-line']); self.zoom_in_btn.setFixedSize(35, 30)
        zoom_layout.addWidget(self.zoom_in_btn)
        self.zoom_fit_btn = QPushButton("Fit"); self.zoom_fit_btn.setFixedSize(35, 30); zoom_layout.addWidget(self.zoom_fit_btn)
        controls_layout.addLayout(zoom_layout); controls_layout.addStretch(2); main_layout.addWidget(controls_panel)
        
        management_dock = QDockWidget("Segment Management", self); management_widget = QWidget(); management_layout = QVBoxLayout(management_widget)
        self.segment_list = QListWidget(); self.segment_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.segment_list.setCursor(Qt.PointingHandCursor); self.segment_list.setContextMenuPolicy(Qt.CustomContextMenu)
        
        self.segment_list.setStyleSheet("""
            QListWidget::item:hover { background-color: #3a3a3a; }
            QListWidget::item:selected { background-color: #4a8cc2; border: 1px solid #6aacf2; color: white; }
        """)

        self.segment_manager = SegmentManager()
        segment_actions_layout = QHBoxLayout()
        self.btn_play_segment = QPushButton("Play"); self.btn_play_all = QPushButton("Play All")
        self.btn_play_segment.setIcon(self.icons['play-line']); self.btn_play_all.setIcon(self.icons['play-list-2-line'])
        segment_actions_layout.addWidget(self.btn_play_segment); segment_actions_layout.addWidget(self.btn_play_all)
        self.properties_group = QGroupBox("Properties"); props_layout = QFormLayout()
        
        self.prop_name = QLineEdit()
        self.prop_start_frame = QSpinBox()
        self.prop_end_frame = QSpinBox()
        self.prop_start_time = QLineEdit()
        self.prop_end_time = QLineEdit()
        self.prop_duration = QLineEdit()

        for field in [self.prop_start_time, self.prop_end_time, self.prop_duration]: field.setReadOnly(True)
        self.btn_jump_to_start = QPushButton("→"); self.btn_jump_to_start.setFixedWidth(30); start_layout = QHBoxLayout(); start_layout.setContentsMargins(0,0,0,0); start_layout.addWidget(self.prop_start_frame); start_layout.addWidget(self.btn_jump_to_start)
        self.btn_jump_to_end = QPushButton("→"); self.btn_jump_to_end.setFixedWidth(30); end_layout = QHBoxLayout(); end_layout.setContentsMargins(0,0,0,0); end_layout.addWidget(self.prop_end_frame); end_layout.addWidget(self.btn_jump_to_end)
        props_layout.addRow("Name:", self.prop_name); props_layout.addRow("Start Frame:", start_layout); props_layout.addRow("End Frame:", end_layout); props_layout.addRow("Start Time:", self.prop_start_time); props_layout.addRow("End Time:", self.prop_end_time); props_layout.addRow("Duration:", self.prop_duration)
        self.properties_group.setLayout(props_layout); self.properties_group.setEnabled(False)
        management_layout.addWidget(self.segment_list); management_layout.addLayout(segment_actions_layout); management_layout.addWidget(self.properties_group)
        management_dock.setWidget(management_widget); self.addDockWidget(Qt.RightDockWidgetArea, management_dock)

        self.status_bar = self.statusBar(); self.time_label = QLabel("Time: --:--:--.---"); self.frame_label = QLabel("Frame: 0"); self.duration_label = QLabel("Duration: --:--:--")
        self.loading_label = QLabel(); self.loading_timer = QTimer(self); self.loading_chars = ["/", "-", "\\", "|"]; self.loading_char_index = 0
        self.loading_label.setToolTip("Generating thumbnails...")
        self.status_bar.addPermanentWidget(self.time_label); self.status_bar.addPermanentWidget(self.frame_label); self.status_bar.addPermanentWidget(self.duration_label)
        
        self.mute_btn = QToolButton(); self.mute_btn.setIcon(self.icons['volume-up-line'])
        self.volume_slider = QSlider(Qt.Horizontal); self.volume_slider.setRange(0, 130); self.volume_slider.setValue(70); self.volume_slider.setFixedWidth(120)
        
        self.setup_menus_and_toolbar()

    def create_separator(self):
        separator = QFrame(); separator.setFrameShape(QFrame.VLine); separator.setFrameShadow(QFrame.Sunken); return separator

    def setup_menus_and_toolbar(self):
        self.actions = {}
        
        # --- Create Actions for ALL commands ---
        self.actions['open_video'] = QAction(self.icons['folder-video-line'], "&Open Video...", self)
        self.actions['open_project'] = QAction(self.icons['play-list-add-line'], "Open &Project...", self)
        self.actions['save_project'] = QAction(self.icons['save-3-line'], "&Save Project As...", self)
        self.actions['export_video'] = QAction(self.icons['file-upload-line'], "&Export Video...", self)
        self.actions['save_snapshot_as'] = QAction(self.icons['camera-line'], "Save Snapshot &As...", self)
        self.actions['quick_snapshot'] = QAction(self.icons['camera-line'], "&Quick Snapshot", self)
        self.actions['exit'] = QAction("E&xit", self)
        self.actions['undo'] = QAction(self.icons['arrow-go-back-line'], "&Undo", self)
        self.actions['redo'] = QAction(self.icons['arrow-go-forward-line'], "&Redo", self)
        self.actions['import_csv'] = QAction(self.icons['file-download-line'], "&Import Segments from CSV...", self)
        self.actions['export_csv'] = QAction(self.icons['file-upload-line'], "Export Segments to CSV...", self)
        self.actions['settings'] = QAction("&Settings...", self)
        self.actions['mark_in'] = QAction(self.icons['mark_in'], "Mark &In Point", self)
        self.actions['mark_out'] = QAction(self.icons['mark_out'], "Mark &Out Point", self)
        self.actions['merge_segments'] = QAction(self.icons['merge-cells-horizontal'], "&Merge Selected Segments", self)
        self.actions['delete_segment'] = QAction(self.icons['delete-bin-line'], "&Delete Selected Segments", self)
        self.actions['zoom_in'] = QAction(self.icons['zoom-in-line'], "Zoom In", self)
        self.actions['zoom_out'] = QAction(self.icons['zoom-out-line'], "Zoom Out", self)
        self.actions['zoom_fit'] = QAction("Fit Timeline to View", self)
        
        # Additional actions for shortcuts
        self.actions['play_selected_segment'] = QAction(self.icons['play-line'], "Play Selected Segment", self)
        self.actions['play_all_segments'] = QAction(self.icons['play-list-2-line'], "Play All Segments", self)
        self.actions['refresh_thumbnails'] = QAction(self.icons['refresh-line'], "Refresh Thumbnails", self)
        self.actions['help_about'] = QAction("Help & About", self)
        
        # Frame navigation actions
        self.actions['prev_frame'] = QAction(self.icons['skip-back-line'], "Previous Frame", self)
        self.actions['next_frame'] = QAction(self.icons['skip-forward-line'], "Next Frame", self)
        self.actions['play_pause'] = QAction(self.icons['play-line'], "Play/Pause", self)
        
        # --- Connect Actions to Handlers ---
        self.actions['open_video'].triggered.connect(self.handle_open_video)
        self.actions['open_project'].triggered.connect(self.handle_open_project)
        self.actions['save_project'].triggered.connect(self.handle_save_project)
        self.actions['export_video'].triggered.connect(self.handle_export_video)
        self.actions['save_snapshot_as'].triggered.connect(self.handle_save_snapshot_as)
        self.actions['quick_snapshot'].triggered.connect(self.handle_quick_snapshot)
        self.actions['exit'].triggered.connect(self.close)
        self.actions['undo'].triggered.connect(self.undo_manager.undo)
        self.actions['redo'].triggered.connect(self.undo_manager.redo)
        self.actions['import_csv'].triggered.connect(self.handle_import_csv)
        self.actions['export_csv'].triggered.connect(self.handle_export_csv)
        self.actions['settings'].triggered.connect(self.handle_settings)
        self.actions['mark_in'].triggered.connect(self.set_in_point)
        self.actions['mark_out'].triggered.connect(self.set_out_point)
        self.actions['merge_segments'].triggered.connect(self.merge_selected_segments)
        self.actions['delete_segment'].triggered.connect(self.delete_selected_segment)
        self.actions['zoom_in'].triggered.connect(lambda: self.zoom_slider.setValue(self.zoom_slider.value() + 50))
        self.actions['zoom_out'].triggered.connect(lambda: self.zoom_slider.setValue(self.zoom_slider.value() - 50))
        self.actions['zoom_fit'].triggered.connect(lambda: self.zoom_slider.setValue(self.zoom_slider.minimum()))
        
        # Connect additional actions
        self.actions['play_selected_segment'].triggered.connect(self.play_selected_segment)
        self.actions['play_all_segments'].triggered.connect(self.play_all_segments)
        self.actions['save_snapshot_as'].triggered.connect(self.handle_save_snapshot_as)
        self.actions['refresh_thumbnails'].triggered.connect(self.load_thumbnails)
        self.actions['help_about'].triggered.connect(self.show_help_about)
        
        # Connect frame navigation actions
        self.actions['prev_frame'].triggered.connect(self.prev_frame_action)
        self.actions['next_frame'].triggered.connect(self.next_frame_action)
        
        # Connect play/pause action
        self.actions['play_pause'].triggered.connect(lambda: self.player.cycle('pause'))

        # --- Set Shortcuts ---
        # File Operations
        self.actions['open_video'].setShortcut(QKeySequence.Open)
        self.actions['save_project'].setShortcut(QKeySequence.Save)
        self.actions['undo'].setShortcut(QKeySequence.Undo)
        self.actions['redo'].setShortcut(QKeySequence.Redo)
        self.actions['export_video'].setShortcut(QKeySequence("Ctrl+E"))
        
        # Segment Management
        self.actions['quick_snapshot'].setShortcut(QKeySequence("F12"))
        self.actions['mark_in'].setShortcut(QKeySequence("I"))
        self.actions['mark_out'].setShortcut(QKeySequence("O"))
        self.actions['delete_segment'].setShortcut(QKeySequence.Delete)
        self.actions['merge_segments'].setShortcut(QKeySequence("M"))
        
        # View Operations
        self.actions['zoom_in'].setShortcut(QKeySequence("Ctrl+Plus"))
        self.actions['zoom_out'].setShortcut(QKeySequence("Ctrl+Minus"))
        self.actions['zoom_fit'].setShortcut(QKeySequence("Ctrl+0"))
        
        # Additional shortcuts
        self.actions['settings'].setShortcut(QKeySequence("Ctrl+,"))
        self.actions['play_selected_segment'].setShortcut(QKeySequence("Enter"))
        self.actions['play_all_segments'].setShortcut(QKeySequence("Ctrl+Enter"))
        self.actions['save_snapshot_as'].setShortcut(QKeySequence("Ctrl+F12"))
        self.actions['refresh_thumbnails'].setShortcut(QKeySequence("F5"))
        self.actions['help_about'].setShortcut(QKeySequence("F1"))
        
        # Frame navigation shortcuts (comma and period)
        self.actions['prev_frame'].setShortcut(QKeySequence(","))
        self.actions['next_frame'].setShortcut(QKeySequence("."))
        
        # Play/Pause shortcut
        self.actions['play_pause'].setShortcut(QKeySequence("Space"))

        # --- Build Toolbar ---
        self.toolbar = self.addToolBar("Main Toolbar")
        # Project Group
        for key in ['open_video', 'save_project', 'export_video']: self.toolbar.addAction(self.actions[key])
        self.toolbar.addSeparator()
        # Edit Group
        for key in ['undo', 'redo']: self.toolbar.addAction(self.actions[key])
        self.toolbar.addSeparator()
        # Segment Group
        for key in ['mark_in', 'mark_out', 'merge_segments', 'delete_segment']: self.toolbar.addAction(self.actions[key])
        self.toolbar.addSeparator()
        # Tools Group
        for key in ['quick_snapshot', 'save_snapshot_as', 'settings']: self.toolbar.addAction(self.actions[key])
        self.toolbar.addSeparator()

        # Set text labels for key actions
        for action_key in ['open_video', 'save_project', 'export_video']:
            tool_button = self.toolbar.widgetForAction(self.actions[action_key])
            if tool_button:
                tool_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Track and Volume Controls
        self.video_track_button = QToolButton(); self.video_track_button.setIcon(self.icons['vidicon-line']); self.video_track_button.setPopupMode(QToolButton.InstantPopup)
        self.audio_track_button = QToolButton(); self.audio_track_button.setIcon(self.icons['headphone-line']); self.audio_track_button.setPopupMode(QToolButton.InstantPopup)
        self.subtitle_track_button = QToolButton(); self.subtitle_track_button.setIcon(self.icons['chat-quote-line']); self.subtitle_track_button.setPopupMode(QToolButton.InstantPopup)
        self.video_track_menu = QMenu(self); self.video_track_button.setMenu(self.video_track_menu); self.video_track_group = QActionGroup(self)
        self.audio_track_menu = QMenu(self); self.audio_track_button.setMenu(self.audio_track_menu); self.audio_track_group = QActionGroup(self)
        self.subtitle_track_menu = QMenu(self); self.subtitle_track_button.setMenu(self.subtitle_track_menu); self.subtitle_track_group = QActionGroup(self)
        for btn in [self.video_track_button, self.audio_track_button, self.subtitle_track_button]: btn.setEnabled(False); self.toolbar.addWidget(btn)
        self.toolbar.addSeparator(); self.toolbar.addWidget(self.mute_btn); self.toolbar.addWidget(self.volume_slider)

        # --- Build Menus ---
        menu_bar = self.menuBar()
        # File Menu
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.actions['open_video'])
        file_menu.addAction(self.actions['open_project'])
        file_menu.addSeparator()
        file_menu.addAction(self.actions['save_project'])
        file_menu.addSeparator()
        import_menu = file_menu.addMenu("&Import")
        import_menu.addAction(self.actions['import_csv'])
        export_menu = file_menu.addMenu("&Export")
        export_menu.addAction(self.actions['export_video'])
        export_menu.addAction(self.actions['export_csv'])
        file_menu.addSeparator()
        file_menu.addAction(self.actions['exit'])
        # Edit Menu
        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.addAction(self.actions['undo'])
        edit_menu.addAction(self.actions['redo'])
        edit_menu.addSeparator()
        edit_menu.addAction(self.actions['settings'])
        # Segment Menu
        segment_menu = menu_bar.addMenu("&Segment")
        segment_menu.addAction(self.actions['mark_in'])
        segment_menu.addAction(self.actions['mark_out'])
        segment_menu.addSeparator()
        segment_menu.addAction(self.actions['delete_segment'])
        segment_menu.addAction(self.actions['merge_segments'])
        segment_menu.addSeparator()
        segment_menu.addAction(self.actions['play_selected_segment'])
        segment_menu.addAction(self.actions['play_all_segments'])
        # View Menu
        view_menu = menu_bar.addMenu("&View")
        view_menu.addAction(self.actions['zoom_in'])
        view_menu.addAction(self.actions['zoom_out'])
        view_menu.addAction(self.actions['zoom_fit'])
        view_menu.addSeparator()
        view_menu.addAction(self.actions['refresh_thumbnails'])
        # Playback Menu
        playback_menu = menu_bar.addMenu("&Playback")
        for key in self.connections:
            if key not in self.actions:
                self.actions[key] = QAction(self.icons.get(key+'-line'), key.replace('_', ' ').title(), self)
                self.actions[key].triggered.connect(self.connections[key].click)
            playback_menu.addAction(self.actions[key])
        
        # Help Menu
        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction(self.actions['help_about'])

    def setup_player(self): self.player = mpv.MPV(wid=str(int(self.video_container.winId())), input_default_bindings=True, osc=False, log_handler=self.handle_mpv_log)
    
    def setup_connections(self):
        self.player.observe_property('time-pos', lambda _, v: self.mpv_signals.time_pos_changed.emit(v) if v is not None else None)
        self.player.observe_property('duration', lambda _, v: self.mpv_signals.duration_changed.emit(v) if v is not None else None)
        self.player.observe_property('paused', lambda _, v: self.mpv_signals.paused_changed.emit(v) if v is not None else None)
        self.player.observe_property('container-fps', lambda _, v: self.mpv_signals.container_fps_changed.emit(v) if v is not None else None)
        self.player.observe_property('track-list', lambda _, v: self.mpv_signals.track_list_changed.emit(v) if v is not None else None)
        self.player.observe_property('volume', lambda _, v: self.mpv_signals.volume_changed.emit(v) if v is not None else None)
        self.player.observe_property('mute', lambda _, v: self.mpv_signals.mute_changed.emit(v) if v is not None else None)
        
        self.mpv_signals.time_pos_changed.connect(self.on_time_update)
        self.mpv_signals.duration_changed.connect(self.on_duration_update)
        self.mpv_signals.paused_changed.connect(self.on_pause_update)
        self.mpv_signals.container_fps_changed.connect(self.on_fps_update)
        self.mpv_signals.track_list_changed.connect(self.on_track_list_update)
        self.mpv_signals.volume_changed.connect(self.on_volume_update)
        self.mpv_signals.mute_changed.connect(self.on_mute_update)

        for name, btn in self.connections.items(): btn.setObjectName(name); btn.clicked.connect(self.handle_button_press)
        self.btn_play_segment.clicked.connect(self.play_selected_segment)
        self.btn_play_all.clicked.connect(self.play_all_segments)
        self.btn_jump_to_start.clicked.connect(self.jump_to_start_frame); self.btn_jump_to_end.clicked.connect(self.jump_to_end_frame)
        self.prop_name.editingFinished.connect(self.apply_properties_changes)
        self.prop_start_frame.editingFinished.connect(self.apply_properties_changes)
        self.prop_end_frame.editingFinished.connect(self.apply_properties_changes)
        self.segment_list.itemDoubleClicked.connect(self.load_segment_for_editing); self.segment_list.itemSelectionChanged.connect(self.on_segment_selection_changed)
        self.segment_list.customContextMenuRequested.connect(self.show_segment_context_menu)
        self.segment_manager.model_changed.connect(self._update_segment_list_view)
        
        self.timeline.mousePressEvent = lambda e: self.timeline_seek(e, self.timeline)
        self.thumbnails.mousePressEvent = lambda e: self.timeline_seek(e, self.thumbnails)
        self.timeline.mouseMoveEvent = lambda e: self.timeline_hover(e, self.timeline)
        self.thumbnails.mouseMoveEvent = lambda e: self.timeline_hover(e, self.thumbnails)
        
        self.timeline.wheelEvent = self.thumbnails.wheelEvent = self.timeline_wheel_event
        
        # Override keyPressEvent for timeline widgets to allow shortcuts to work
        self.timeline.keyPressEvent = lambda e: self.timeline_key_press_event(e, self.timeline)
        self.thumbnails.keyPressEvent = lambda e: self.timeline_key_press_event(e, self.thumbnails)
        self.zoom_slider.valueChanged.connect(self.redraw_timeline); self.zoom_in_btn.clicked.connect(self.actions['zoom_in'].trigger)
        self.zoom_out_btn.clicked.connect(self.actions['zoom_out'].trigger); self.zoom_fit_btn.clicked.connect(self.actions['zoom_fit'].trigger)
        self.undo_manager.undo_stack_changed.connect(self.actions['undo'].setEnabled); self.undo_manager.redo_stack_changed.connect(self.actions['redo'].setEnabled)
        self.undo_manager.command_executed.connect(self.mark_as_dirty)
        self.loading_timer.timeout.connect(self._update_loading_animation)
        self.mute_btn.clicked.connect(self.toggle_mute); self.volume_slider.valueChanged.connect(self.set_volume)
        self.setup_timeline_sync(); self.setup_tooltips()
    
    def set_player_controls_enabled(self, enabled):
        for action in self.actions.values():
            action.setEnabled(enabled)
        
        if not enabled:
            # Always allow opening a new file or exiting
            self.actions['open_video'].setEnabled(True)
            self.actions['open_project'].setEnabled(True)
            self.actions['exit'].setEnabled(True)
            self.actions['settings'].setEnabled(True)
        
        for widget in list(self.connections.values()) + [self.btn_play_segment, self.btn_play_all, self.zoom_out_btn, self.zoom_slider, self.zoom_in_btn, self.zoom_fit_btn, self.mute_btn, self.volume_slider]:
            widget.setEnabled(enabled)

    def on_volume_update(self, value):
        if not self.volume_slider.isSliderDown(): self.volume_slider.setValue(int(value))
        if value > 0: self.last_volume = value
    def on_mute_update(self, muted):
        self.mute_btn.setIcon(self.icons['volume-mute-line'] if muted else self.icons['volume-up-line']); self.volume_slider.setEnabled(not muted)
    def set_volume(self, value):
        self.player.volume = value;
        if self.player.mute and value > 0: self.player.mute = False
    def toggle_mute(self): self.player.mute = not self.player.mute
    
    def on_time_update(self, value):
        try:
            if not self.player or self.player.core_shutdown:
                return
                
            if self.is_playing_segment and self.current_frame >= self.segment_playback_end:
                self.player.pause = True; self.cancel_segment_playback()
            if self.duration > 0 and self.fps > 0:
                self.current_frame = int(value * self.fps)
                self.time_label.setText(f"Time: {self.format_time(value, True)}"); self.frame_label.setText(f"Frame: {self.current_frame}")
                
                if self.in_point >= 0 and self.out_point == -1:
                    self.redraw_timeline()
                else:
                    self.redraw_playhead()
        except (mpv.ShutdownError, AttributeError):
            return

    def on_duration_update(self, value):
        self.duration = value; self.duration_label.setText(f"Duration: {self.format_time(self.duration)}")
        if self.fps > 0:
            self.total_frames = int(self.duration * self.fps)
            for spinbox in [self.prop_start_frame, self.prop_end_frame]:
                spinbox.setRange(0, self.total_frames)
            
            self.set_player_controls_enabled(True)
            self.load_thumbnails(); self.redraw_timeline()
            if self.pending_project_segments is not None:
                segments_data = [(d['start_frame'], d['end_frame'], QColor(d['color']), d['name']) for d in self.pending_project_segments]
                self.segment_manager.set_segments(segments_data); self.undo_manager.clear(); self.pending_project_segments = None
    
    def on_fps_update(self, value): self.fps = value; self.segment_manager.fps = value; self.on_duration_update(self.duration)
    def on_pause_update(self, is_paused):
        if is_paused: self.cancel_segment_playback()
        self.connections['play_pause'].setIcon(self.icons['play-line'] if is_paused else self.icons['pause-line'])
    def on_track_list_update(self, tracks):
        for menu, group, btn, slot, ttype in [(self.video_track_menu, self.video_track_group, self.video_track_button, self.change_video_track, 'video'),(self.audio_track_menu, self.audio_track_group, self.audio_track_button, self.change_audio_track, 'audio'),(self.subtitle_track_menu, self.subtitle_track_group, self.subtitle_track_button, self.change_subtitle_track, 'sub')]:
            menu.clear()
            for action in group.actions(): group.removeAction(action)
            track_list = [t for t in tracks if t.get('type') == ttype] if tracks else []
            self._populate_track_menu(track_list, menu, group, btn, slot)
    def _populate_track_menu(self, tracks, menu, group, button, slot):
        button.setEnabled(len(tracks) > 1)
        for track in tracks:
            title = f"#{track['id']}"; lang = track.get('lang'); t_title = track.get('title')
            if lang: title += f" [{lang}]"
            if t_title: title += f" - {t_title}"
            action = QAction(title, self, checkable=True); action.setData(track['id']); action.triggered.connect(slot); menu.addAction(action); group.addAction(action)
            if track.get('selected'): action.setChecked(True)
        if button == self.subtitle_track_button and tracks:
            menu.addSeparator(); none_action = QAction("None", self, checkable=True); none_action.setData(-1)
            none_action.triggered.connect(lambda: setattr(self.player, 'sid', 'no')); menu.addAction(none_action); group.addAction(none_action)
            if self.player.sid in ['no', None]: none_action.setChecked(True)
    def change_video_track(self): self.player.vid = self.sender().data()
    def change_audio_track(self): self.player.aid = self.sender().data()
    def change_subtitle_track(self): self.player.sid = self.sender().data()
    def handle_button_press(self):
        actions={'jump_start':lambda:setattr(self.player,'time_pos',0),
                 'jump_end':lambda:setattr(self.player,'time_pos',self.duration-0.05),
                 'prev_frame':lambda:self.player.command('frame-back-step'),
                 'next_frame':lambda:self.player.command('frame-step'),
                 'prev_boundary': self.seek_to_prev_boundary,
                 'next_boundary': self.seek_to_next_boundary,
                 'play_pause':lambda:self.player.cycle('pause')}
        action = actions.get(self.sender().objectName());
        if action: action()
    
    def _load_video(self, path):
        if self.thumb_loader_thread and self.thumb_loader_thread.isRunning():
            self.thumb_loader_worker.stop()
            self.thumb_loader_thread.quit()
            self.thumb_loader_thread.wait()
            self.thumb_loader_thread = None

        self.set_player_controls_enabled(False)
        self.video_path = path
        
        self.duration = self.fps = self.total_frames = self.current_frame = 0
        self.in_point, self.out_point = -1, -1
        self._color_idx = 0
        
        self.timeline_scene.clear()
        self.thumbnails_scene.clear()
        self.playhead = None
        self.segment_list.clear()
        self.segment_manager.set_segments([])
        self.undo_manager.clear()
        self.mark_as_dirty(False)
        
        for btn in [self.video_track_button, self.audio_track_button, self.subtitle_track_button]:
            btn.setEnabled(False)
            btn.menu().clear()

        self.player.loadfile(self.video_path)
        self.player.pause = True
        self.clear_in_out_points()
        
        # Setup keyboard shortcuts after video is loaded
        self.setup_keyboard_shortcuts()

    def handle_open_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video File");
        if path: self._load_video(path)

    def handle_open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Project File", "", "JSON Files (*.json)");
        if path:
            self.handle_open_project_path(path)

    def handle_open_project_path(self, path):
        try:
            with open(path, 'r') as f:
                project_data = json.load(f)

            video_file = Path(project_data['video_path'])
            if not video_file.exists():
                QMessageBox.warning(self, "File Not Found", f"The video file for this project could not be found at:\n\n{video_file}\n\nPlease locate the file.")
                new_path, _ = QFileDialog.getOpenFileName(self, f"Find Video: {video_file.name}")
                if not new_path:
                    return
                project_data['video_path'] = new_path

            self.pending_project_segments = project_data['segments']
            self._load_video(project_data['video_path'])
            self.status_bar.showMessage(f"Project '{os.path.basename(path)}' loaded.", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load project file:\n{e}")

    def handle_save_project(self):
        if not self.video_path: QMessageBox.warning(self, "Warning", "Please open a video before saving a project."); return
        path, _ = QFileDialog.getSaveFileName(self, "Save Project File", "", "JSON Files (*.json)");
        if not path: return
        try:
            segments_data = [{'start_frame': s.start_frame, 'end_frame': s.end_frame, 'color': s.color.name(), 'name': s.name} for s in self.segment_manager.get_all_segments()]
            project_data = {'video_path': self.video_path, 'segments': segments_data}
            with open(path, 'w') as f: json.dump(project_data, f, indent=4)
            self.status_bar.showMessage(f"Project saved to '{os.path.basename(path)}'", 4000)
            self.mark_as_dirty(False)
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to save project file:\n{e}")
    
    def handle_save_snapshot_as(self):
        if not self.video_path:
            QMessageBox.warning(self, "Warning", "Please open a video first.")
            return
        video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        default_filename = f"{video_name}_frame_{self.current_frame}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Save Snapshot As...", default_filename, "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)")
        if not path:
            return
        try:
            self.player.screenshot_to_file(path)
            self.status_bar.showMessage(f"Snapshot saved to {os.path.basename(path)}", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save snapshot:\n{e}")

    def handle_quick_snapshot(self):
        if not self.video_path: return
        
        save_path = self.settings.value("snapshot/quickSavePath", "", str)
        if not save_path or not os.path.isdir(save_path):
            QMessageBox.warning(self, "Quick Snapshot Error", "The directory for quick snapshots is not set or is invalid.\nPlease set it in Edit > Settings > Snapshots.")
            return
            
        fmt = self.settings.value("snapshot/format", "PNG", str).lower()
        template = self.settings.value("snapshot/template", "{filename}_frame_{frame_num}", str)
        
        filename = template.format(
            filename=Path(self.video_path).stem,
            frame_num=self.current_frame,
            time_ms=int((self.player.time_pos or 0) * 1000)
        )
        
        full_path = Path(save_path) / f"{sanitize_filename(filename)}.{fmt}"
        
        try:
            self.player.screenshot_to_file(str(full_path))
            self.status_bar.showMessage(f"Snapshot saved: {full_path.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save snapshot:\n{e}")

    def handle_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
        
    def handle_import_csv(self):
        if not (self.video_path and self.fps > 0): QMessageBox.warning(self, "Warning", "Please open a video file first."); return
        path, _ = QFileDialog.getOpenFileName(self, "Import Segments CSV", "", "CSV Files (*.csv)");
        if not path: return
        old_segments = [(s.start_frame, s.end_frame, s.color, s.name) for s in self.segment_manager.get_all_segments()]
        try:
            with open(path, 'r', newline='') as f:
                new_segments_data = []
                for i, row in enumerate(csv.reader(f)):
                    if len(row) >= 2 and row[0].isdigit() and row[1].isdigit():
                        color = self.segment_colors[i % len(self.segment_colors)]; new_segments_data.append((int(row[0]), int(row[1]), color, ""))
            new_segments_for_cmd = [(d[0], d[1], d[2], d[3]) for d in new_segments_data]
            self.undo_manager.execute(ImportSegmentsCommand(self.segment_manager, old_segments, new_segments_for_cmd))
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to import CSV file:\n{e}")
    def handle_export_csv(self):
        segments = self.segment_manager.get_all_segments()
        if not segments: QMessageBox.warning(self, "Warning", "No segments to export."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export Segments CSV", "", "CSV Files (*.csv)")
        if not path: return
        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f); writer.writerow(['start_frame', 'end_frame', 'name'])
                sorted_segments = sorted(segments, key=lambda s: s.start_frame)
                for seg in sorted_segments: writer.writerow([seg.start_frame, seg.end_frame, seg.name])
            self.status_bar.showMessage(f"Successfully exported {len(segments)} segments to {os.path.basename(path)}", 4000)
        except Exception as e: QMessageBox.critical(self, "Error", f"Failed to export CSV file:\n{e}")
    def set_in_point(self):
        self.in_point = self.current_frame; self.out_point = -1; self.status_bar.showMessage(f"IN: {self.in_point}", 2000)
        self.actions['mark_in'].setEnabled(False)
        self.actions['mark_out'].setEnabled(True)
        self.redraw_timeline()
    def set_out_point(self):
        if self.in_point == -1: return
        if self.current_frame > self.in_point:
            self.out_point = self.current_frame; self.status_bar.showMessage(f"OUT: {self.out_point}", 2000)
            self.add_segment_from_in_out()
    def add_segment_from_in_out(self):
        if self.in_point >= 0 and self.out_point > self.in_point:
            color = self.segment_colors[self._color_idx % len(self.segment_colors)]
            self._color_idx += 1
            data = (self.in_point, self.out_point, color, ""); self.undo_manager.execute(AddSegmentCommand(self.segment_manager, data))
            self.clear_in_out_points()
    def delete_selected_segment(self):
        selected_items = self.segment_list.selectedItems()
        if not selected_items: return
        row = self.segment_list.row(selected_items[0])
        if row >= 0:
            seg = self.segment_manager.get_all_segments()[row]; data = (seg.start_frame, seg.end_frame, seg.color, seg.name)
            self.undo_manager.execute(DeleteSegmentCommand(self.segment_manager, row, data))
    def load_segment_for_editing(self, item):
        row = self.segment_list.row(item)
        if self.fps > 0: self.player.time_pos = item.data(Qt.UserRole).start_frame / self.fps
        self.segment_list.setCurrentRow(row)
    def clear_in_out_points(self):
        self.in_point, self.out_point = -1, -1
        self.actions['mark_in'].setEnabled(True)
        self.actions['mark_out'].setEnabled(False)
        self.redraw_timeline()
    def cancel_segment_playback(self): self.is_playing_segment = False; self.segment_playback_end = -1
    def on_segment_selection_changed(self):
        num_selected = len(self.segment_list.selectedItems())
        self.actions['delete_segment'].setEnabled(num_selected > 0)
        self.actions['merge_segments'].setEnabled(num_selected > 1)
        self.btn_play_segment.setEnabled(num_selected == 1)
        self.properties_group.setEnabled(num_selected == 1)

        if num_selected == 1:
            seg = self.segment_list.selectedItems()[0].data(Qt.UserRole)
            self.prop_name.setText(seg.name)
            self.prop_start_frame.setValue(seg.start_frame)
            self.prop_end_frame.setValue(seg.end_frame)
            if self.fps > 0:
                duration_s = (seg.end_frame - seg.start_frame) / self.fps
                self.prop_start_time.setText(self.format_time(seg.start_frame / self.fps, True))
                self.prop_end_time.setText(self.format_time(seg.end_frame / self.fps, True))
                self.prop_duration.setText(f"{duration_s:.3f}s ({seg.end_frame - seg.start_frame} frames)")
        else:
            for field in [self.prop_name, self.prop_start_time, self.prop_end_time, self.prop_duration]: field.clear()
            self.prop_start_frame.setValue(0)
            self.prop_end_frame.setValue(0)
            
    def apply_properties_changes(self):
        row = self.segment_list.currentRow()
        if row < 0: return
        
        if isinstance(self.sender(), QLineEdit) and not self.sender().isModified():
             return

        try:
            new_start, new_end, new_name = self.prop_start_frame.value(), self.prop_end_frame.value(), self.prop_name.text()
            if new_start >= new_end:
                QMessageBox.warning(self, "Invalid Input", "Start frame must be less than end frame."); self.on_segment_selection_changed(); return
            old_seg = self.segment_manager.get_all_segments()[row]
            old_data = (old_seg.start_frame, old_seg.end_frame, old_seg.color, old_seg.name)
            new_data = (new_start, new_end, old_seg.color, new_name)
            if old_data != new_data:
                self.undo_manager.execute(UpdateSegmentCommand(self.segment_manager, row, old_data, new_data))
                self.status_bar.showMessage("Segment properties updated.", 3000)
            if isinstance(self.sender(), QLineEdit):
                self.sender().setModified(False)
        except (ValueError, TypeError): 
            QMessageBox.warning(self, "Invalid Input", "Frame numbers must be valid integers."); self.on_segment_selection_changed()

    def jump_to_start_frame(self):
        if self.fps > 0: self.player.time_pos = self.prop_start_frame.value() / self.fps
    def jump_to_end_frame(self):
        if self.fps > 0: self.player.time_pos = self.prop_end_frame.value() / self.fps
    
    def show_segment_context_menu(self, pos):
        if not self.segment_list.itemAt(pos): return
        num_selected = len(self.segment_list.selectedItems())
        menu = QMenu()
        play = menu.addAction(self.icons['play-line'], "Play Segment")
        seek = menu.addAction("Seek to Start")
        play.setEnabled(num_selected == 1)
        seek.setEnabled(num_selected == 1)
        menu.addSeparator()
        menu.addAction(self.actions['merge_segments'])
        menu.addAction(self.actions['delete_segment'])
        menu.addSeparator()
        change_color = menu.addAction("Change Color")
        change_color.setEnabled(num_selected > 0)
        
        action = menu.exec(self.segment_list.mapToGlobal(pos))
        
        if action == play: self.play_selected_segment()
        elif action == seek: self.load_segment_for_editing(self.segment_list.selectedItems()[0])
        elif action == change_color: self.change_selected_segment_color()

    def change_selected_segment_color(self):
        selected_items = self.segment_list.selectedItems()
        if not selected_items: return

        initial_color = selected_items[0].data(Qt.UserRole).color
        new_color = QColorDialog.getColor(initial_color, self, "Select Segment Color")

        if new_color.isValid():
            for item in selected_items:
                row = self.segment_list.row(item)
                old_seg = self.segment_manager.get_all_segments()[row]
                old_data = (old_seg.start_frame, old_seg.end_frame, old_seg.color, old_seg.name)
                new_data = (old_seg.start_frame, old_seg.end_frame, new_color, old_seg.name)
                self.undo_manager.execute(UpdateSegmentCommand(self.segment_manager, row, old_data, new_data))

    def merge_selected_segments(self):
        selected_items = self.segment_list.selectedItems()
        if len(selected_items) < 2: return
        segs = sorted([{'index': self.segment_list.row(i), 'segment': i.data(Qt.UserRole)} for i in selected_items], key=lambda x: x['segment'].start_frame)
        for i in range(len(segs) - 1):
            if segs[i]['segment'].end_frame < segs[i+1]['segment'].start_frame - 1:
                QMessageBox.warning(self, "Merge Failed", "Segments must be adjacent or overlapping to be combined."); return
        new_start = segs[0]['segment'].start_frame; new_end = max(s['segment'].end_frame for s in segs)
        merged_data = (new_start, new_end, segs[0]['segment'].color, f"Merged [{new_start}-{new_end}]")
        self.undo_manager.execute(MergeSegmentsCommand(self.segment_manager, [s['index'] for s in segs], merged_data))
    def get_sorted_boundaries(self):
        boundaries = set(); [boundaries.update([s.start_frame, s.end_frame]) for s in self.segment_manager.get_all_segments()]; return sorted(list(boundaries))
    def seek_to_next_boundary(self):
        boundaries = self.get_sorted_boundaries(); current_f = self.current_frame
        for frame in boundaries:
            if frame > current_f: self.player.time_pos = frame / self.fps; return
    def seek_to_prev_boundary(self):
        boundaries = self.get_sorted_boundaries(); current_f = self.current_frame
        for frame in reversed(boundaries):
            if frame < current_f: self.player.time_pos = frame / self.fps; return
    def play_selected_segment(self):
        selected = self.segment_list.selectedItems()
        if len(selected) != 1: return
        seg = selected[0].data(Qt.UserRole)
        self.is_playing_segment = True; self.segment_playback_end = seg.end_frame
        self.player.time_pos = seg.start_frame / self.fps; self.player.pause = False
    def _get_or_create_cached_video_path(self) -> str:
        if not self.video_path: return ""
        try:
            video_file = Path(self.video_path); cache_folder = video_file.parent / ".powertrim_cache"
            cache_folder.mkdir(parents=True, exist_ok=True)
            hash_digest = hashlib.sha1(str(video_file).encode('utf-8')).hexdigest()[:12]
            safe_name = f"{hash_digest}{video_file.suffix}"; safe_path = cache_folder / safe_name
            if not safe_path.exists():
                try:
                    os.link(self.video_path, safe_path); self.status_bar.showMessage("Created secure playback cache.", 3000)
                except OSError: return self.video_path
            return str(safe_path).replace('\\', '/')
        except Exception: return self.video_path
    def play_all_segments(self):
        self.player.pause = True; all_segments = self.segment_manager.get_all_segments()
        if not all_segments: QMessageBox.warning(self, "Playback", "No segments to play."); return
        if not self.fps > 0: QMessageBox.critical(self, "Error", "Video FPS not determined."); return
        safe_video_path = self._get_or_create_cached_video_path()
        if not safe_video_path: QMessageBox.critical(self, "Error", "Video path is invalid."); return
        sorted_segments = sorted(all_segments, key=lambda s: s.start_frame)
        edl_parts = [f"{safe_video_path},{s.start_frame/self.fps:.6f},{(s.end_frame-s.start_frame)/self.fps:.6f}" for s in sorted_segments]
        edl_string = "edl://" + ";".join(edl_parts)
        self.status_bar.showMessage("Launching external player for preview...", 3000)
        try:
            subprocess.run([resolve_tool("mpv"), edl_string], 
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except FileNotFoundError: QMessageBox.critical(self, "Error", "mpv executable not found.\nPlease ensure mpv is installed and in your system's PATH.")
        self.status_bar.showMessage("Preview finished.", 3000)
    def handle_mpv_log(self, level, prefix, text):
        if level in ['warn', 'error', 'fatal']: self.status_bar.showMessage(f"[{prefix}] {text.strip()}", 4000)
    
    def timeline_seek(self, event, view):
        self.cancel_segment_playback()
        scene_width = view.scene().width()
        if self.duration > 0 and event.button() == Qt.LeftButton and scene_width > 0:
            self.player.time_pos = self.duration * (view.mapToScene(event.position().toPoint()).x() / scene_width)

    def timeline_hover(self, event, view):
        if not self.settings.value("playback/hoverScrub", True, bool):
            return
        
        try:
            if self.player.pause == True and self.duration > 0:
                scene_width = view.scene().width()
                if scene_width > 0:
                    hover_pos_x = view.mapToScene(event.position().toPoint()).x()
                    self.player.time_pos = self.duration * (hover_pos_x / scene_width)
        except (mpv.ShutdownError, AttributeError):
            pass
        
        QGraphicsView.mouseMoveEvent(view, event)

    def timeline_wheel_event(self, event):
        if event.modifiers() & Qt.ControlModifier: self.zoom_slider.setValue(self.zoom_slider.value() + (50 if event.angleDelta().y() > 0 else -50))
        else: QGraphicsView.wheelEvent(self.timeline, event)
    def redraw_timeline(self):
        if not (self.duration > 0 and self.total_frames > 0): return
        
        self.timeline_scene.clear()
        self.playhead = None
        
        zoom=self.zoom_slider.value()/100.0; width,height=self.timeline.width()*zoom,self.timeline.height(); self.timeline_scene.setSceneRect(0,0,width,height); self.timeline_scene.addRect(0,0,width,height,QPen(Qt.NoPen),QBrush(QColor("#222222")))
        for item in self.thumbnails_scene.items():
            if not isinstance(item, QGraphicsPixmapItem): self.thumbnails_scene.removeItem(item)
        thumb_width = self.thumbnails_scene.itemsBoundingRect().width()
        for seg in self.segment_manager.get_all_segments():
            x_s, x_e = (seg.start_frame/self.total_frames)*width, (seg.end_frame/self.total_frames)*width
            self.timeline_scene.addRect(x_s,5,x_e-x_s,height-10,QPen(seg.color.darker(150)),seg.color)
            if thumb_width > 0:
                rect = self.thumbnails_scene.addRect((seg.start_frame/self.total_frames)*thumb_width,0,(seg.end_frame/self.total_frames)*thumb_width-(seg.start_frame/self.total_frames)*thumb_width,self.thumbnails.height(),QPen(seg.color.darker(150)),seg.color); rect.setZValue(5)
        if self.in_point >= 0: self.draw_in_out_markers(width, height)
        num_ticks=int(width/100) or 1; interval_s=self.duration/num_ticks
        for i in range(num_ticks+1):
            x=(i*interval_s/self.duration)*width; self.timeline_scene.addLine(x,height-15,x,height,QPen(Qt.white))
            text=self.timeline_scene.addText(self.format_time(i*interval_s),QFont("Segoe UI",8)); text.setDefaultTextColor(Qt.white); text.setPos(x+2,height-35)
        self.redraw_playhead()
    
    def draw_in_out_markers(self, width, height):
        x_in = (self.in_point / self.total_frames) * width
        end_frame = self.out_point if self.out_point > self.in_point else self.current_frame
        x_out = (end_frame / self.total_frames) * width
        self.timeline_scene.addRect(x_in, 0, x_out - x_in, height, QPen(Qt.NoPen), QColor(255, 255, 255, 40))
        
        in_pen = QPen(QColor(0, 255, 255), 2)
        self.timeline_scene.addLine(x_in, 0, x_in, height, in_pen)
        in_poly = QPolygonF([QPointF(x_in, 0), QPointF(x_in + 8, 0), QPointF(x_in, 8)])
        self.timeline_scene.addPolygon(in_poly, in_pen, QBrush(QColor(0, 255, 255)))
        
        if self.out_point > self.in_point:
            x_out_marker = (self.out_point / self.total_frames) * width
            out_pen = QPen(QColor(255, 255, 0), 2)
            self.timeline_scene.addLine(x_out_marker, 0, x_out_marker, height, out_pen)
            out_poly = QPolygonF([QPointF(x_out_marker, 0), QPointF(x_out_marker - 8, 0), QPointF(x_out_marker, 8)])
            self.timeline_scene.addPolygon(out_poly, out_pen, QBrush(QColor(255, 255, 0)))

    def redraw_playhead(self):
        try:
            if not self.player or self.player.core_shutdown:
                return

            if self.playhead:
                try: self.timeline_scene.removeItem(self.playhead)
                except RuntimeError: pass
            if self.duration>0:
                pos = self.player.time_pos or 0; x = (pos/self.duration)*self.timeline_scene.width()
                self.playhead = self.timeline_scene.addLine(x,0,x,self.timeline.height(),QPen(QColor("red"),2)); self.playhead.setZValue(12)
                if self.timeline.horizontalScrollBar().isVisible():
                    self.timeline.centerOn(self.playhead)
        except (mpv.ShutdownError, AttributeError):
            return
    
    def _update_segment_list_view(self):
        current_selection_rows = [self.segment_list.row(item) for item in self.segment_list.selectedItems()]
        self.segment_list.clear()

        for seg in self.segment_manager.get_all_segments():
            item = QListWidgetItem()
            item.setData(Qt.UserRole, seg)

            item_widget = QWidget()
            main_layout = QHBoxLayout(item_widget)
            main_layout.setContentsMargins(5, 3, 5, 3)
            main_layout.setSpacing(8)

            color_swatch = QFrame()
            color_swatch.setFixedSize(8, 32)
            color_swatch.setStyleSheet(f"background-color: {seg.color.name()}; border-radius: 3px;")
            
            text_widget = QWidget()
            text_layout = QVBoxLayout(text_widget)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(0)

            name_label = QLabel(seg.name)
            font = name_label.font(); font.setBold(True); font.setPointSize(10)
            name_label.setFont(font)

            duration_s = (seg.end_frame - seg.start_frame) / self.fps if self.fps > 0 else 0
            details_text = f"{seg.start_frame} → {seg.end_frame}  ({duration_s:.2f}s)"
            details_label = QLabel(details_text)
            details_label.setStyleSheet("color: #a0a0a0;")

            text_layout.addWidget(name_label)
            text_layout.addWidget(details_label)

            main_layout.addWidget(color_swatch)
            main_layout.addWidget(text_widget)
            
            item.setSizeHint(item_widget.sizeHint())
            
            self.segment_list.addItem(item)
            self.segment_list.setItemWidget(item, item_widget)
        
        for row in current_selection_rows:
            if 0 <= row < self.segment_list.count():
                self.segment_list.item(row).setSelected(True)
        
        self.redraw_timeline()
        self.on_segment_selection_changed()

    def load_thumbnails(self):
        if not (self.video_path and self.duration > 0): return
        if self.thumb_loader_thread and self.thumb_loader_thread.isRunning():
            self.thumb_loader_worker.stop(); self.thumb_loader_thread.quit(); self.thumb_loader_thread.wait()
        self.thumbnails_scene.clear()
        # Inform the user visually in the thumbnails view as well
        self._show_thumbnails_loading_overlay()
        self.thumb_loader_thread = QThread(); self.thumb_loader_worker = ThumbnailLoader(self.video_path,self.duration,75); self.thumb_loader_worker.moveToThread(self.thumb_loader_thread)
        self.thumb_loader_worker.thumbnail_ready.connect(self.add_thumbnail_to_scene)
        self.thumb_loader_thread.started.connect(self.thumb_loader_worker.run)
        self.thumb_loader_worker.finished.connect(self._on_thumbnails_finished)
        self.thumb_loader_worker.finished.connect(self.thumb_loader_worker.deleteLater)
        self.thumb_loader_thread.finished.connect(self.thumb_loader_thread.deleteLater)
        self.thumb_loader_thread.finished.connect(self._clear_thumb_thread_ref)
        self.status_bar.addPermanentWidget(self.loading_label); self.loading_timer.start(100); self.thumb_loader_thread.start()
    
    @Slot()
    def _clear_thumb_thread_ref(self):
        self.thumb_loader_thread = None
        self.thumb_loader_worker = None

    def add_thumbnail_to_scene(self, _, image):
        pixmap = QPixmap.fromImage(image.scaledToHeight(70,Qt.SmoothTransformation)); item = QGraphicsPixmapItem(pixmap)
        item.setPos(self.thumbnails_scene.itemsBoundingRect().width(), 0); self.thumbnails_scene.addItem(item)
        self.thumbnails_scene.setSceneRect(self.thumbnails_scene.itemsBoundingRect()); self.redraw_timeline()
    def format_time(self, seconds, with_ms=False):
        if seconds is None: seconds=0
        m, s = divmod(seconds,60); h, m = divmod(m,60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}" + (f".{int((seconds-int(seconds))*1000):03d}" if with_ms else "")
    def setup_timeline_sync(self):
        self.timeline_scrollbar = self.timeline.horizontalScrollBar(); self.thumbnails_scrollbar = self.thumbnails.horizontalScrollBar()
        self.timeline_scrollbar.valueChanged.connect(self.sync_thumbnails_from_timeline)
        self.thumbnails_scrollbar.valueChanged.connect(self.sync_timeline_from_thumbnails)
    def sync_thumbnails_from_timeline(self, value):
        if self._is_scrolling_programmatically: return
        self._is_scrolling_programmatically = True; self.thumbnails_scrollbar.setValue(value); self._is_scrolling_programmatically = False
    def sync_timeline_from_thumbnails(self, value):
        if self._is_scrolling_programmatically: return
        self._is_scrolling_programmatically = True; self.timeline_scrollbar.setValue(value); self._is_scrolling_programmatically = False
    def _update_loading_animation(self):
        char = self.loading_chars[self.loading_char_index]; self.loading_label.setText(f" Generating Thumbnails {char}")
        self.loading_char_index = (self.loading_char_index + 1) % len(self.loading_chars)
    def _on_thumbnails_finished(self):
        self.loading_timer.stop()
        self.status_bar.removeWidget(self.loading_label)
        self._hide_thumbnails_loading_overlay()

    def _show_thumbnails_loading_overlay(self):
        try:
            self._hide_thumbnails_loading_overlay()
            self.thumbnails_scene.setSceneRect(0, 0, max(1, self.thumbnails.width()), self.thumbnails.height())
            text = "Generating thumbnails..."
            self.thumbs_loading_text_item = self.thumbnails_scene.addText(text, QFont("Segoe UI", 10))
            self.thumbs_loading_text_item.setDefaultTextColor(Qt.lightGray)
            rect = self.thumbs_loading_text_item.boundingRect()
            x = (self.thumbnails_scene.width() - rect.width()) / 2
            y = (self.thumbnails_scene.height() - rect.height()) / 2
            self.thumbs_loading_text_item.setPos(max(0, x), max(0, y))
        except Exception:
            self.thumbs_loading_text_item = None

    def _hide_thumbnails_loading_overlay(self):
        if self.thumbs_loading_text_item:
            try:
                self.thumbnails_scene.removeItem(self.thumbs_loading_text_item)
            except RuntimeError:
                pass
        self.thumbs_loading_text_item = None
    
    def setup_tooltips(self):
        self.actions['open_video'].setToolTip("Open a new video file (Ctrl+O)")
        self.actions['save_project'].setToolTip("Save the current segments to a project file (Ctrl+S)")
        self.actions['export_video'].setToolTip("Export the defined segments to video files (Ctrl+E)")
        self.actions['save_snapshot_as'].setToolTip("Save the current frame as an image with a dialog (Ctrl+F12)")
        self.actions['quick_snapshot'].setToolTip("Instantly save the current frame to the configured directory (F12)")
        self.actions['undo'].setToolTip("Undo last action (Ctrl+Z)")
        self.actions['redo'].setToolTip("Redo last undone action (Ctrl+Y)")
        self.actions['mark_in'].setToolTip("Mark In Point (I)")
        self.actions['mark_out'].setToolTip("Mark Out Point (O)")
        self.actions['delete_segment'].setToolTip("Delete Selected Segments (Del)")
        self.actions['merge_segments'].setToolTip("Merge Selected Segments (M)")
        self.actions['play_selected_segment'].setToolTip("Play Selected Segment (Enter)")
        self.actions['play_all_segments'].setToolTip("Play All Segments (Ctrl+Enter)")
        self.actions['zoom_in'].setToolTip("Zoom In (Ctrl+Plus)")
        self.actions['zoom_out'].setToolTip("Zoom Out (Ctrl+Minus)")
        self.actions['zoom_fit'].setToolTip("Fit Timeline to View (Ctrl+0)")
        self.actions['refresh_thumbnails'].setToolTip("Refresh Thumbnails (F5)")
        self.actions['settings'].setToolTip("Settings (Ctrl+,)")
        self.actions['help_about'].setToolTip("Help & About (F1)")
        self.connections['prev_frame'].setToolTip("Go to Previous Frame (,)")
        self.connections['next_frame'].setToolTip("Go to Next Frame (.)")
        self.connections['play_pause'].setToolTip("Play/Pause (Space)")
        self.connections['jump_start'].setToolTip("Jump to Start (Home)")
        self.connections['jump_end'].setToolTip("Jump to End (End)")
        self.connections['prev_boundary'].setToolTip("Previous Boundary (Ctrl+Left)")
        self.connections['next_boundary'].setToolTip("Next Boundary (Ctrl+Right)")
        
        # Add tooltips for global navigation shortcuts
        self.timeline.setToolTip("Timeline - Use arrow keys to navigate: Left/Right (5s), Up/Down (1min), Home/End (start/end)")
        self.thumbnails.setToolTip("Thumbnails - Use arrow keys to navigate: Left/Right (5s), Up/Down (1min), Home/End (start/end)")

    def closeEvent(self, event):
        # Prompt to save if there are unsaved changes
        if self.is_project_dirty:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes to your project. Do you want to save before exiting?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Cancel:
                event.ignore(); return
            if reply == QMessageBox.Save:
                # Attempt to save; if user cancels save dialog, abort close
                prev_dirty = self.is_project_dirty
                self.handle_save_project()
                if prev_dirty and self.is_project_dirty:
                    # Save was likely cancelled or failed
                    event.ignore(); return

        if self.export_thread and self.export_thread.isRunning():
            reply = QMessageBox.question(self, "Export in Progress", "An export job is currently running. Are you sure you want to quit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: event.ignore(); return
            self.export_worker.stop(); self.export_thread.quit(); self.export_thread.wait()
        
        if self.thumb_loader_thread and self.thumb_loader_thread.isRunning():
            self.thumb_loader_worker.stop(); self.thumb_loader_thread.quit(); self.thumb_loader_thread.wait()
        
        if self.player: self.player.terminate()
        event.accept()

    def handle_export_video(self):
        if not self.segment_manager.get_all_segments():
            QMessageBox.warning(self, "Export Error", "There are no segments to export."); return
        if not self.video_path: return

        try:
            video_meta = get_video_metadata(Path(self.video_path))
            all_tracks = video_meta.get('streams', [])
        except (RuntimeError, FileNotFoundError) as e:
            QMessageBox.critical(self, "Error", f"Could not get video metadata for export: {e}")
            return

        export_options_dialog = ExportDialog(self, Path(self.video_path).stem, all_tracks, video_meta, self.settings)
        if export_options_dialog.exec():
            settings = export_options_dialog.get_settings()
            settings.update(export_options_dialog.get_track_settings())
            
            output_dir_setting = self.settings.value("export/defaultDirectory", "", str)

            if settings['merge']:
                file_filter = "MKV Video (*.mkv)" if settings['video_mode'] == 'ffv1' else "MP4 Video (*.mp4)"
                default_name = sanitize_filename(f"{settings['output_template'].format(filename=Path(self.video_path).stem)}")
                output_path, _ = QFileDialog.getSaveFileName(self, "Save Merged Video As...", os.path.join(output_dir_setting, default_name), file_filter)
                if not output_path: return
                settings['output_file'] = output_path
            else:
                output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory for Clips...", output_dir_setting)
                if not output_dir: return
                settings['output_dir'] = output_dir

            settings["input_video"] = Path(self.video_path)
            settings["mode"] = "frames"
            settings["segments_raw"] = [(s.start_frame, s.end_frame) for s in self.segment_manager.get_all_segments()]

            self.export_dialog = ExportStatusDialog(self, settings)
            
            self.export_thread = QThread()
            self.export_worker = ExportWorker(settings)
            self.export_worker.moveToThread(self.export_thread)
            
            self.export_dialog.cancelled.connect(self.export_worker.stop)
            self.export_worker.clip_started.connect(self.export_dialog.update_overall_progress)
            self.export_worker.step_changed.connect(self.export_dialog.update_step_text)
            self.export_worker.progress_updated.connect(self.export_dialog.update_current_progress)
            self.export_worker.finished.connect(self.on_export_finished)
            self.export_worker.error.connect(self.on_export_error)
            
            self.export_thread.started.connect(self.export_worker.run)
            self.export_thread.started.connect(self.export_dialog.start_timer)
            self.export_thread.finished.connect(self.export_thread.deleteLater)
            self.export_thread.finished.connect(self.export_worker.deleteLater)
            
            self.export_thread.start()
            self.export_dialog.show()

    def on_export_finished(self, result_path):
        if self.export_dialog:
            self.export_dialog.close()
        
        if self.export_thread:
            self.export_thread.quit()
            self.export_thread.wait()
        self.export_thread = None
        
        msg = "Video export completed successfully!"
        if result_path == "Cancelled":
            msg = "Export was cancelled by the user."
        elif result_path and Path(result_path).is_dir():
            if self.export_dialog and self.export_dialog.open_folder_checkbox.isChecked():
                try:
                    os.startfile(result_path) # For Windows
                except AttributeError:
                    subprocess.run(['xdg-open', result_path], 
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) # For Linux
            msg += f"\n\nClips saved in folder:\n{result_path}"
        elif result_path:
            if self.export_dialog and self.export_dialog.open_folder_checkbox.isChecked():
                try:
                    os.startfile(os.path.dirname(result_path))
                except AttributeError:
                    subprocess.run(['xdg-open', os.path.dirname(result_path)],
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            msg += f"\n\nOutput saved to:\n{result_path}"

        QMessageBox.information(self, "Export Finished", msg)
        self.export_dialog = None

    def on_export_error(self, error_message):
        if self.export_dialog:
            self.export_dialog.close()

        if self.export_thread:
            self.export_thread.quit()
            self.export_thread.wait()
        self.export_thread = None
        QMessageBox.critical(self, "Export Failed", f"An error occurred during export:\n\n{error_message}")
        self.export_dialog = None
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            if Path(file_path).suffix.lower() in ['.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv', '.json']:
                event.acceptProposedAction()

    def dropEvent(self, event):
        file_path = event.mimeData().urls()[0].toLocalFile()
        if file_path.lower().endswith('.json'):
            self.handle_open_project_path(file_path)
        else:
            self._load_video(file_path)

    def mark_as_dirty(self, dirty=True):
        if self.is_project_dirty == dirty:
            return
        self.is_project_dirty = dirty
        self._update_window_title()

    def _update_window_title(self):
        title = "PowerTrim"
        if self.video_path:
            dirty_indicator = "*" if self.is_project_dirty else ""
            title = f"{Path(self.video_path).name}{dirty_indicator} - {title}"
        self.setWindowTitle(title)
    
    def show_help_about(self):
        """Show help and about dialog with keyboard shortcuts."""
        shortcuts_text = """
<b>PowerTrim - Video Trimming Application</b><br><br>

<b>Keyboard Shortcuts:</b><br><br>

<b>File Operations:</b><br>
• Ctrl+O - Open Video<br>
• Ctrl+S - Save Project<br>
• Ctrl+E - Export Video<br>
• Ctrl+Q - Quit<br><br>

<b>Playback Control:</b><br>
• Space - Play/Pause<br>
• Left/Right - Seek 5 seconds<br>
• Up/Down - Seek 1 minute<br>
• , - Previous frame<br>
• . - Next frame<br>
• Home - Jump to start<br>
• End - Jump to end<br>
• Ctrl+Left/Right - Previous/Next boundary<br><br>

<b>Segment Management:</b><br>
• I - Mark In Point<br>
• O - Mark Out Point<br>
• Delete - Delete selected segment<br>
• M - Merge selected segments<br>
• Enter - Play selected segment<br>
• Ctrl+Enter - Play all segments<br><br>

<b>Timeline Navigation:</b><br>
• Ctrl+Plus - Zoom in<br>
• Ctrl+Minus - Zoom out<br>
• Ctrl+0 - Zoom fit<br>
• Ctrl+Mouse Wheel - Zoom timeline<br><br>

<b>Snapshots:</b><br>
• F12 - Quick snapshot<br>
• Ctrl+F12 - Save snapshot as<br><br>

<b>Other:</b><br>
• F1 - This help dialog<br>
• F5 - Refresh thumbnails<br>
• Ctrl+, - Settings<br><br>

<b>Version:</b> 1.0<br>
<b>Built with:</b> PySide6, python-mpv, FFmpeg, SmartCut
        """
        
        QMessageBox.information(self, "Help & About - PowerTrim", shortcuts_text)
    
    def setup_keyboard_shortcuts(self):
        """Setup additional keyboard shortcuts using QShortcut."""
        # Clear existing shortcuts
        if hasattr(self, 'shortcuts'):
            for shortcut in self.shortcuts.values():
                shortcut.deleteLater()
        
        if not self.video_path:
            return
            
        # Arrow key navigation shortcuts
        self.shortcuts = {}
        
        # Left/Right - Seek 5 seconds
        self.shortcuts['seek_left'] = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcuts['seek_left'].activated.connect(self.seek_5_seconds_backward)
        
        self.shortcuts['seek_right'] = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcuts['seek_right'].activated.connect(self.seek_5_seconds_forward)
        
        # Up/Down - Seek 1 minute
        self.shortcuts['seek_up'] = QShortcut(QKeySequence(Qt.Key_Up), self)
        self.shortcuts['seek_up'].activated.connect(self.seek_1_minute_backward)
        
        self.shortcuts['seek_down'] = QShortcut(QKeySequence(Qt.Key_Down), self)
        self.shortcuts['seek_down'].activated.connect(self.seek_1_minute_forward)
        
        # Home/End - Jump to start/end
        self.shortcuts['jump_home'] = QShortcut(QKeySequence(Qt.Key_Home), self)
        self.shortcuts['jump_home'].activated.connect(self.jump_to_start)
        
        self.shortcuts['jump_end'] = QShortcut(QKeySequence(Qt.Key_End), self)
        self.shortcuts['jump_end'].activated.connect(self.jump_to_end)
        
        # Ctrl + Arrow keys for boundary navigation
        self.shortcuts['prev_boundary'] = QShortcut(QKeySequence("Ctrl+Left"), self)
        self.shortcuts['prev_boundary'].activated.connect(self.seek_to_prev_boundary)
        
        self.shortcuts['next_boundary'] = QShortcut(QKeySequence("Ctrl+Right"), self)
        self.shortcuts['next_boundary'].activated.connect(self.seek_to_next_boundary)
        
        # Ctrl + Q to quit
        self.shortcuts['quit'] = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.shortcuts['quit'].activated.connect(self.close)
    
    def seek_5_seconds_backward(self):
        """Seek 5 seconds backward."""
        if not self.video_path:
            return
        current_pos = self.player.time_pos or 0
        new_pos = max(0, current_pos - 5)
        self.player.time_pos = new_pos
    
    def seek_5_seconds_forward(self):
        """Seek 5 seconds forward."""
        if not self.video_path:
            return
        current_pos = self.player.time_pos or 0
        new_pos = min(self.duration, current_pos + 5)
        self.player.time_pos = new_pos
    
    def seek_1_minute_backward(self):
        """Seek 1 minute backward."""
        if not self.video_path:
            return
        current_pos = self.player.time_pos or 0
        new_pos = max(0, current_pos - 60)
        self.player.time_pos = new_pos
    
    def seek_1_minute_forward(self):
        """Seek 1 minute forward."""
        if not self.video_path:
            return
        current_pos = self.player.time_pos or 0
        new_pos = min(self.duration, current_pos + 60)
        self.player.time_pos = new_pos
    
    def jump_to_start(self):
        """Jump to the start of the video."""
        if not self.video_path:
            return
        self.player.time_pos = 0
    
    def jump_to_end(self):
        """Jump to the end of the video."""
        if not self.video_path:
            return
        self.player.time_pos = max(0, self.duration - 0.05)
    
    def prev_frame_action(self):
        """Previous frame action."""
        if not self.video_path:
            return
        self.player.command('frame-back-step')
    
    def next_frame_action(self):
        """Next frame action."""
        if not self.video_path:
            return
        self.player.command('frame-step')
    
    def timeline_key_press_event(self, event, view):
        """Handle key press events in timeline widgets."""
        # Let the main window handle navigation shortcuts
        key = event.key()
        modifiers = event.modifiers()
        
        # Check if this is one of our navigation shortcuts
        if (modifiers == Qt.NoModifier and key in [Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End]) or \
           (modifiers == Qt.ControlModifier and key in [Qt.Key_Left, Qt.Key_Right]) or \
           (modifiers == Qt.ControlModifier and key == Qt.Key_Q):
            # Let the main window handle these shortcuts
            event.ignore()
            return
        
        # For other keys, let the default QGraphicsView behavior handle them
        QGraphicsView.keyPressEvent(view, event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setOrganizationName("PowerTrim")
    app.setApplicationName("PowerTrimGUI")
    window = ProTrimmerWindow()
    window.show()
    sys.exit(app.exec())