"""
Step-through review of uncertain ('?') neuron IDs, e.g. proposed by the ID-transfer pipeline.

The reviewer walks through every neuron whose ID1 still contains a '?', selects it in the trace explorer, and lets
the user accept, reject or correct the proposal with one click / key. Optionally, a second, already-annotated
recording (the "reference") can be loaded; the trace of the neuron with the same name in the reference is then
plotted next to / on top of the current neuron's trace to help decide.

All decisions go through ``NeuronNameEditor`` (accept/reject/correct/undo), so they appear in the name table and in
napari immediately, and are written to disk by the normal "Save all to disk".
"""
import logging
import os
from typing import Callable, Dict, Optional, Tuple

import numpy as np
from PyQt5.QtCore import Qt, QThread, QSettings, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QFileDialog, QShortcut, QCheckBox,
    QSizePolicy, QScrollArea, QFrame, QSlider
)

# Same recipe for both recordings so the shapes are comparable (matches calc_default_traces' recommended settings)
TRACE_OPTIONS = dict(channel_mode='dr_over_r_50', calculation_mode='integration', remove_outliers=True,
                     filter_mode='rolling_mean')


def zscore(y) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    sd = np.nanstd(y)
    if not np.isfinite(sd) or sd == 0:
        return y - np.nanmean(y)
    return (y - np.nanmean(y)) / sd


def trace_in_seconds(project_data, neuron_name: str) -> Tuple[np.ndarray, np.ndarray]:
    """Trace of one neuron with a time axis in seconds (falls back to volumes if the frame rate is unknown)"""
    # calculate_traces replaces project_data._trace_plotter; restore it so the explorer's own plotting is unaffected
    previous_plotter = project_data._trace_plotter
    try:
        t, y = project_data.calculate_traces(neuron_name=neuron_name, **TRACE_OPTIONS)
    finally:
        project_data._trace_plotter = previous_plotter
    t = np.asarray(t, dtype=float)
    try:
        fps = float(project_data.physical_unit_conversion.volumes_per_second)
        if fps > 0:
            t = t / fps
    except Exception:
        pass
    return t, np.asarray(y, dtype=float)


def recording_acquisition(project_data):
    """(volumes per second, number of volumes), each None if unavailable"""
    try:
        rate = float(project_data.physical_unit_conversion.volumes_per_second)
    except Exception:
        rate = None
    try:
        n_volumes = int(project_data.num_frames)
    except Exception:
        n_volumes = None
    return rate, n_volumes


def describe_trace(t, y) -> str:
    """'300 s, 16% missing': why a trace may look shorter or gappy next to another recording"""
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    duration = (t[-1] - t[0]) if len(t) > 1 else 0.0
    missing = float(np.mean(~np.isfinite(y))) if len(y) else 1.0
    text = f"{duration:.0f} s"
    return f"{text}, {missing:.0%} missing" if missing >= 0.01 else text


def crop_window(t, y, start: float, length: float):
    """Samples with start <= t - t[0] <= start + length, re-zeroed so the window begins at t = 0 (real seconds)"""
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    if len(t) == 0:
        return t, y
    rel = t - t[0]
    keep = (rel >= start) & (rel <= start + length)
    return rel[keep] - start, y[keep]


def _resample(t, y, grid):
    """Linear resampling onto ``grid`` that bridges NaN gaps (only used to score similarity)"""
    ok = np.isfinite(y)
    return np.interp(grid, t[ok], y[ok]) if ok.sum() > 1 else np.full(len(grid), np.nan)


def best_window_start(t_long, y_long, t_short, y_short, dt: float = 1.0, step: float = 5.0):
    """
    Start (seconds into the longer recording) of the window that correlates best with the shorter trace

    Both are compared in real time on a common grid. Returns (start_s, pearson_r). This is only a convenience for
    finding a stretch worth looking at: with enough candidate windows some will correlate by chance.
    """
    t_long, t_short = np.asarray(t_long, dtype=float), np.asarray(t_short, dtype=float)
    t_long, t_short = t_long - t_long[0], t_short - t_short[0]
    length = t_short[-1]
    if t_long[-1] <= length:
        return 0.0, float('nan')
    grid_short = np.arange(0.0, length, dt)
    grid_long = np.arange(0.0, t_long[-1], dt)
    ys, yl = _resample(t_short, np.asarray(y_short, dtype=float), grid_short), \
        _resample(t_long, np.asarray(y_long, dtype=float), grid_long)
    ys = zscore(ys)
    n = len(grid_short)
    best_r, best_start = -np.inf, 0.0
    for i in range(0, len(grid_long) - n + 1, max(1, int(round(step / dt)))):
        w = yl[i:i + n]
        if np.nanstd(w) == 0 or not np.isfinite(w).all():
            continue
        r = float(np.mean(ys * zscore(w)))
        if r > best_r:
            best_r, best_start = r, float(grid_long[i])
    return best_start, (best_r if np.isfinite(best_r) else float('nan'))


class ReferenceRecording:
    """A second, annotated recording, looked up by neuron *name* (e.g. 'AVAL') rather than by 'neuron_012'"""

    def __init__(self, project_data):
        self.dat = project_data
        mapping = project_data.neuron_name_to_manual_id_mapping(
            confidence_threshold=0, flip_names_and_ids=True, remove_unnamed_neurons=True)
        # ID -> that recording's internal neuron name; uncertain IDs in the reference are not a valid reference
        self.id_to_neuron: Dict[str, str] = {str(k): str(v) for k, v in mapping.items() if "?" not in str(k)}
        self._trace_cache: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}  # flipping through neurons stays instant

    @property
    def label(self) -> str:
        return os.path.basename(str(self.dat.project_dir))

    def acquisition(self):
        """(volumes per second, number of volumes) of this recording; None where unknown"""
        return recording_acquisition(self.dat)

    def lookup(self, neuron_id: str) -> Optional[str]:
        """The reference's spelling of this ID (case-insensitive), or None if it isn't annotated there"""
        if neuron_id in self.id_to_neuron:
            return neuron_id
        lower = {k.lower(): k for k in self.id_to_neuron}
        return lower.get(neuron_id.lower())

    def has(self, neuron_id: str) -> bool:
        return self.lookup(neuron_id) is not None

    def similar(self, neuron_id: str, n_chars: int = 3):
        """Annotated IDs that share a prefix, e.g. AVAL -> AVAR, AVAL2, to hint at a left/right mix-up"""
        prefix = neuron_id[:n_chars].lower()
        return sorted(k for k in self.id_to_neuron if k.lower().startswith(prefix) and k.lower() != neuron_id.lower())

    def trace(self, neuron_id: str) -> Tuple[np.ndarray, np.ndarray]:
        key = self.lookup(neuron_id)
        if key not in self._trace_cache:
            self._trace_cache[key] = trace_in_seconds(self.dat, self.id_to_neuron[key])
        return self._trace_cache[key]


class _ReferenceLoader(QThread):
    """Loading a project takes several seconds (network share); never do it on the GUI thread"""
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            from wbfm.utils.projects.finished_project_data import ProjectData
            dat = ProjectData.load_final_project_data_from_config(self.path)
            self.loaded.emit(ReferenceRecording(dat))
        except Exception as e:  # report anything to the user rather than dying silently in the thread
            logging.exception("Failed to load reference recording")
            self.failed.emit(str(e))


class QuestionMarkReviewer(QWidget):
    """
    Parameters
    ----------
    editor: NeuronNameEditor holding the annotation dataframe
    project_data: the recording being annotated (for its trace)
    select_neuron: callable(original_name) that selects the neuron in the trace explorer (optional)
    """

    def __init__(self, editor, project_data=None, select_neuron: Optional[Callable[[str], None]] = None,
                 parent=None):
        super().__init__(parent)
        self.editor = editor
        self.dat = project_data
        self.select_neuron = select_neuron
        self.reference: Optional[ReferenceRecording] = None
        self._loader: Optional[_ReferenceLoader] = None
        self.queue = []
        self.pos = 0
        self.counts = dict(accepted=0, rejected=0, corrected=0)
        self._window_fraction = 0.0  # where the window sits in the longer recording (0 = start, 1 = end)
        self._own_trace_cache = (None, None, None)  # (neuron, t, y) so dragging the slider doesn't recompute

        self._build_ui()
        self._bind_shortcuts()
        self.refresh_queue(select=False)  # don't move the explorer's current neuron just by opening the panel

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # Everything lives in a scroll area: in a short dock the plot must not be squeezed out of sight
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)

        self.progress_label = QLabel()
        layout.addWidget(self.progress_label)

        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        row = QHBoxLayout()
        self.accept_button = QPushButton("✓ Accept  (Ctrl+Y)")
        self.accept_button.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.accept_button.clicked.connect(self.accept_current)
        self.reject_button = QPushButton("✗ Reject  (Ctrl+N)")
        self.reject_button.setStyleSheet("background-color: #b71c1c; color: white; font-weight: bold;")
        self.reject_button.clicked.connect(self.reject_current)
        row.addWidget(self.accept_button)
        row.addWidget(self.reject_button)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.back_button = QPushButton("◀ Back  (Ctrl+B)")
        self.back_button.clicked.connect(self.previous)
        self.skip_button = QPushButton("Skip ▶  (Ctrl+K)")
        self.skip_button.clicked.connect(self.skip)
        self.undo_button = QPushButton("Undo  (Ctrl+U)")
        self.undo_button.clicked.connect(self.undo)
        row.addWidget(self.back_button)
        row.addWidget(self.skip_button)
        row.addWidget(self.undo_button)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.correct_edit = QLineEdit()
        self.correct_edit.setPlaceholderText("Different name, e.g. AVAR")
        self.correct_edit.returnPressed.connect(self.correct_current)
        self.correct_button = QPushButton("Use this name")
        self.correct_button.clicked.connect(self.correct_current)
        row.addWidget(self.correct_edit)
        row.addWidget(self.correct_button)
        layout.addLayout(row)

        # --- reference recording
        self.reference_label = QLabel("Reference recording (annotated, to compare against):")
        layout.addWidget(self.reference_label)
        row = QHBoxLayout()
        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText("Path to project folder or project_config.yaml")
        settings = QSettings("ZimmerLab", "WBFM")
        self.reference_edit.setText(str(settings.value("reference_recording", "")))
        self.reference_edit.returnPressed.connect(self.load_reference)
        browse = QPushButton("…")
        browse.setFixedWidth(28)
        browse.clicked.connect(self._browse_reference)
        self.reference_button = QPushButton("Load")
        self.reference_button.clicked.connect(self.load_reference)
        row.addWidget(self.reference_edit)
        row.addWidget(browse)
        row.addWidget(self.reference_button)
        layout.addLayout(row)

        self.reference_status = QLabel("No reference loaded")
        self.reference_status.setWordWrap(True)
        layout.addWidget(self.reference_status)

        self.overlay_checkbox = QCheckBox("Overlay (otherwise stacked)")
        self.overlay_checkbox.setChecked(True)
        self.overlay_checkbox.stateChanged.connect(self.update_comparison_plot)
        layout.addWidget(self.overlay_checkbox)
        self.window_checkbox = QCheckBox("Same time window (real time, no stretching)")
        self.window_checkbox.setToolTip(
            "Recordings differ in length and frame rate. On: the longer recording is cut to the length of the "
            "shorter one and both are drawn at true speed, so shapes look as they normally do. "
            "Off: both whole recordings in real seconds.")
        self.window_checkbox.setChecked(True)
        self.window_checkbox.stateChanged.connect(self.update_comparison_plot)
        layout.addWidget(self.window_checkbox)
        row = QHBoxLayout()
        self.window_slider = QSlider(Qt.Horizontal)
        self.window_slider.setRange(0, 1000)
        self.window_slider.setToolTip("Which part of the longer recording to show")
        self.window_slider.valueChanged.connect(self._on_window_slider)
        self.best_window_button = QPushButton("Most similar window")
        self.best_window_button.setToolTip("Jump to the stretch of the longer trace that correlates best with the "
                                           "other one (a starting point, not proof of a match)")
        self.best_window_button.clicked.connect(self.jump_to_best_window)
        row.addWidget(self.window_slider)
        row.addWidget(self.best_window_button)
        layout.addLayout(row)
        self.window_label = QLabel("")
        self.window_label.setWordWrap(True)
        layout.addWidget(self.window_label)
        self.zscore_checkbox = QCheckBox("Z-score traces")
        self.zscore_checkbox.setChecked(True)
        self.zscore_checkbox.stateChanged.connect(self.update_comparison_plot)
        layout.addWidget(self.zscore_checkbox)

        # Matplotlib is imported lazily; the panel works without any reference
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        self.figure = Figure(figsize=(4, 3), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setMinimumHeight(240)
        layout.addWidget(self.canvas)
        self.canvas.setVisible(False)

    def _bind_shortcuts(self):
        # Scoped to this widget; napari-canvas keys are bound separately by the trace explorer
        for key, func in [("Ctrl+Y", self.accept_current), ("Ctrl+N", self.reject_current),
                          ("Ctrl+K", self.skip), ("Ctrl+B", self.previous), ("Ctrl+U", self.undo)]:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(func)

    # ------------------------------------------------------------------ queue
    @property
    def current(self) -> Optional[str]:
        return self.queue[self.pos] if self.queue else None

    def refresh_queue(self, keep: Optional[str] = None, select: bool = True):
        """Re-read the '?' neurons from the editor; keeps pointing at ``keep`` if it is still uncertain"""
        self.queue = self.editor.uncertain_neurons()
        if keep in self.queue:
            self.pos = self.queue.index(keep)
        else:
            self.pos = min(self.pos, max(len(self.queue) - 1, 0))
        self._show_current(select=select)

    def _advance_after_decision(self, decided: str):
        # The decided neuron has left the queue; the next one has slid into the same position
        self.queue = self.editor.uncertain_neurons()
        if self.pos >= len(self.queue):
            self.pos = 0
        self._show_current()

    def skip(self):
        if self.queue:
            self.pos = (self.pos + 1) % len(self.queue)
            self._show_current()

    def previous(self):
        if self.queue:
            self.pos = (self.pos - 1) % len(self.queue)
            self._show_current()

    # ------------------------------------------------------------------ decisions
    def accept_current(self):
        name = self.current
        if name and self.editor.accept_question_mark(name):
            self.counts['accepted'] += 1
            self._advance_after_decision(name)

    def reject_current(self):
        name = self.current
        if name and self.editor.reject_question_mark(name):
            self.counts['rejected'] += 1
            self._advance_after_decision(name)

    def correct_current(self):
        name = self.current
        new_name = self.correct_edit.text().strip()
        if name and new_name and self.editor.correct_question_mark(name, new_name):
            self.counts['corrected'] += 1
            self.correct_edit.clear()
            self._advance_after_decision(name)

    def undo(self):
        name = self.editor.undo_review_action()
        if name is not None:
            self.refresh_queue(keep=name)

    # ------------------------------------------------------------------ display
    def _show_current(self, select: bool = True):
        name = self.current
        total = len(self.queue)
        done = sum(self.counts.values())
        has_any = name is not None
        for b in (self.accept_button, self.reject_button, self.skip_button, self.back_button,
                  self.correct_button, self.correct_edit):
            b.setEnabled(has_any)
        self.undo_button.setEnabled(bool(self.editor._review_undo_stack))

        if not has_any:
            self.progress_label.setText(f"Nothing left to review — {self.counts['accepted']} accepted, "
                                        f"{self.counts['rejected']} rejected, {self.counts['corrected']} corrected "
                                        "(remember to Save all to disk)")
            self.name_label.setText("")
            self.info_label.setText("")
            self.update_comparison_plot()
            return

        self.progress_label.setText(f"{self.pos + 1} of {total} uncertain   •   {done} decided "
                                    f"({self.counts['accepted']}✓ {self.counts['rejected']}✗ "
                                    f"{self.counts['corrected']} corrected)")
        row = self.editor._row_of_neuron(name)
        df = self.editor.df
        proposal = str(df.at[row, self.editor.manual_id_column_name])
        self.name_label.setText(f"{name}  →  {proposal}")
        extra = []
        for col in (self.editor.certainty_column_name, self.editor.notes_column_name):
            if col in df.columns and str(df.at[row, col]).strip() not in ("", "nan"):
                extra.append(f"{col}: {df.at[row, col]}")
        self.info_label.setText("   |   ".join(extra))

        if select and self.select_neuron is not None:
            try:
                self.select_neuron(name)
            except Exception as e:  # e.g. neuron not in the explorer's dropdown
                logging.warning(f"Could not select {name} in the explorer: {e}")
        self.update_comparison_plot()

    # ------------------------------------------------------------------ reference recording
    def _browse_reference(self):
        start = self.reference_edit.text() or ""
        path = QFileDialog.getExistingDirectory(self, "Reference project folder", start)
        if path:
            self.reference_edit.setText(path)
            self.load_reference()

    def load_reference(self):
        path = self.reference_edit.text().strip().strip('"')
        if not path:
            return
        if not os.path.exists(path):
            self.reference_status.setText(f"Path does not exist: {path}")
            return
        if self._loader is not None and self._loader.isRunning():
            return
        self.reference_status.setText("Loading reference recording (runs in the background)…")
        self.reference_button.setEnabled(False)
        self._loader = _ReferenceLoader(path, self)
        self._loader.loaded.connect(self._on_reference_loaded)
        self._loader.failed.connect(self._on_reference_failed)
        self._loader.start()

    def set_reference(self, reference: ReferenceRecording):
        self.reference = reference
        QSettings("ZimmerLab", "WBFM").setValue("reference_recording", self.reference_edit.text().strip())
        text = f"Reference: {reference.label} — {len(reference.id_to_neuron)} named neurons"
        ref_rate, ref_volumes = reference.acquisition()
        if ref_rate and ref_volumes:
            text += f"\n{ref_volumes} volumes at {ref_rate:.2f}/s = {ref_volumes / ref_rate:.0f} s"
        own_rate, own_volumes = recording_acquisition(self.dat) if self.dat is not None else (None, None)
        if own_rate and ref_rate and abs(own_rate - ref_rate) / own_rate > 0.05:
            text += (f"\n⚠ different frame rate than this recording ({ref_rate:.2f} vs {own_rate:.2f} volumes/s): "
                     f"dynamics will look faster or slower")
        if own_volumes and ref_volumes and own_rate and ref_rate:
            own_s, ref_s = own_volumes / own_rate, ref_volumes / ref_rate
            if max(own_s, ref_s) > 1.35 * min(own_s, ref_s):
                text += f"\n⚠ very different length ({ref_s:.0f} s vs {own_s:.0f} s): compare using the time window"
        self.reference_status.setText(text)
        self.reference_button.setEnabled(True)
        self.update_comparison_plot()

    def _on_reference_loaded(self, reference):
        self.set_reference(reference)

    def _on_reference_failed(self, msg):
        self.reference_button.setEnabled(True)
        self.reference_status.setText(f"Failed to load reference: {msg}")

    @staticmethod
    def proposed_id(proposal: str) -> str:
        return proposal.replace("?", "").strip()

    def _message_plot(self, text: str):
        ax = self.figure.add_subplot(111)
        ax.text(0.5, 0.5, text, ha='center', va='center', wrap=True)
        ax.set_axis_off()
        self.canvas.draw_idle()

    def _own_trace(self, name):
        cached_name, t, y = self._own_trace_cache
        if cached_name != name:
            t, y = trace_in_seconds(self.dat, name)
            self._own_trace_cache = (name, t, y)
        return t, y

    def _on_window_slider(self, value):
        self._window_fraction = value / 1000.0
        self.update_comparison_plot()

    def _comparison_data(self):
        """Both traces in real seconds, windowed to equal length if requested. Returns None if not plottable"""
        name = self.current
        proposal = self.proposed_id(str(self.editor.df.at[self.editor._row_of_neuron(name),
                                                         self.editor.manual_id_column_name]))
        key = self.reference.lookup(proposal)
        if key is None:
            hint = self.reference.similar(proposal)
            extra = f"\n\nSimilar names there: {', '.join(hint[:8])}" if hint else ""
            self._message_plot(f"'{proposal}' is not annotated in the reference recording{extra}")
            return None
        try:
            t_mine, y_mine = self._own_trace(name)
            t_ref, y_ref = self.reference.trace(key)
        except Exception as e:
            logging.warning(f"Could not compute comparison traces for {name}: {e}")
            self._message_plot(f"Trace failed: {e}")
            return None
        if len(t_mine) != len(y_mine) or len(t_ref) != len(y_ref):
            self._message_plot("Trace and time axis have different lengths; cannot plot")
            return None
        return name, key, (t_mine, y_mine), (t_ref, y_ref)

    def _window_for(self, mine, ref):
        """(start, length, which) of the cut applied to the longer recording; which is 'mine', 'ref' or None"""
        dur_mine = mine[0][-1] - mine[0][0] if len(mine[0]) > 1 else 0.0
        dur_ref = ref[0][-1] - ref[0][0] if len(ref[0]) > 1 else 0.0
        if not self.window_checkbox.isChecked() or abs(dur_mine - dur_ref) < 1.0:
            return 0.0, min(dur_mine, dur_ref), None
        which = 'mine' if dur_mine > dur_ref else 'ref'
        length = min(dur_mine, dur_ref)
        longest = max(dur_mine, dur_ref)
        return self._window_fraction * (longest - length), length, which

    def jump_to_best_window(self):
        if self.reference is None or self.current is None:
            return
        data = self._comparison_data()
        if data is None:
            return
        _, _, mine, ref = data
        dur_mine, dur_ref = mine[0][-1] - mine[0][0], ref[0][-1] - ref[0][0]
        if abs(dur_mine - dur_ref) < 1.0:
            return
        long_, short = (mine, ref) if dur_mine > dur_ref else (ref, mine)
        start, r = best_window_start(long_[0], long_[1], short[0], short[1])
        spare = max(abs(dur_mine - dur_ref), 1e-9)
        self.window_slider.setValue(int(round(1000 * start / spare)))  # triggers a redraw
        self.window_label.setText(self.window_label.text().split("   (best r")[0] + f"   (best r = {r:.2f})")

    def update_comparison_plot(self, *_):
        name = self.current
        if self.reference is None or name is None or self.dat is None:
            self.canvas.setVisible(False)
            return
        self.canvas.setVisible(True)
        self.figure.clear()
        data = self._comparison_data()
        if data is None:
            return
        name, key, mine, ref = data

        # Describe the full traces (duration, missing data) before any cutting
        mine_label = f"this: {name} ({describe_trace(*mine)})"
        ref_label = f"reference: {key} ({describe_trace(*ref)})"

        start, length, which = self._window_for(mine, ref)
        t_mine, y_mine = mine
        t_ref, y_ref = ref
        if which == 'mine':
            t_mine, y_mine = crop_window(t_mine, y_mine, start, length)
            mine_label += f" – showing {start:.0f}–{start + length:.0f} s"
        elif which == 'ref':
            t_ref, y_ref = crop_window(t_ref, y_ref, start, length)
            ref_label += f" – showing {start:.0f}–{start + length:.0f} s"
        t_mine, t_ref = t_mine - (t_mine[0] if len(t_mine) else 0), t_ref - (t_ref[0] if len(t_ref) else 0)
        self.window_slider.setEnabled(which is not None)
        self.best_window_button.setEnabled(which is not None)
        self.window_label.setText(
            f"Showing {start:.0f}–{start + length:.0f} s of the longer recording" if which else
            "Full recordings in real time" if not self.window_checkbox.isChecked() else
            "Both recordings have the same length")

        if self.zscore_checkbox.isChecked():
            y_mine, y_ref = zscore(y_mine), zscore(y_ref)

        if self.overlay_checkbox.isChecked():
            ax = self.figure.add_subplot(111)
            ax.plot(t_mine, y_mine, color='k', lw=1, label=mine_label)
            ax.plot(t_ref, y_ref, color='tab:orange', lw=1, alpha=0.8, label=ref_label)
            ax.legend(fontsize=7, loc='upper center', bbox_to_anchor=(0.5, -0.18), ncol=1, frameon=False)
            ax.set_xlabel("Time (s)")
        else:
            ax1 = self.figure.add_subplot(211)
            ax2 = self.figure.add_subplot(212, sharex=ax1)
            ax1.plot(t_mine, y_mine, color='k', lw=1)
            ax1.set_title(mine_label, fontsize=8)
            ax2.plot(t_ref, y_ref, color='tab:orange', lw=1)
            ax2.set_title(ref_label, fontsize=8)
            ax2.set_xlabel("Time (s)")
        self.canvas.draw_idle()
