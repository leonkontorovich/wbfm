"""
Modern Qt Recording Dashboard & Launcher for WBFM Trace Explorer.
Provides an interactive, searchable overview of recordings across project directories,
live pipeline status inspection, detailed recording diagnostics, and fast one-click
launch into Napari Trace Explorer.

Usage:
    python launch_gui.py [project_path] [--fast] [--load-tracklets] [--debug]
"""
import sys
import os
import argparse
import json
import re
import datetime
import time
import logging
import functools
from typing import Optional, List, Dict, Tuple, Any

# Add wbfm to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wbfm.utils.projects.annotation_files import newest_annotation_file, annotation_excel_file

from qtpy.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QProgressBar, QFrame,
    QSpacerItem, QSizePolicy, QMessageBox, QMenu, QAction, QSplitter,
    QScrollArea, QSplashScreen, QLayout, QComboBox
)
from qtpy.QtCore import Qt, QThread, Signal, Slot, QTimer, QSettings, QPoint, QRect, QSize
from qtpy.QtGui import QColor, QFont, QIcon, QBrush, QPixmap, QPainter

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".recent_projects.json")
CUSTOM_ROOTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".custom_roots.json")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".dashboard_cache.json")
INCOMPLETE_CACHE_RETRY_S = 300  # re-read a project whose last metadata read failed after this many seconds
APP_ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wbfm", "gui", "icons", "wbfm_dashboard.ico")


def apply_app_icon(app) -> None:
    """Window and taskbar icon for the dashboard; purely cosmetic, so never fails"""
    if not os.path.exists(APP_ICON_FILE):
        return
    try:
        if sys.platform == "win32":
            import ctypes
            # Own taskbar entry, so Windows shows this icon instead of python.exe's
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ZimmerLab.WBFM.Dashboard")
        app.setWindowIcon(QIcon(APP_ICON_FILE))
    except Exception as e:
        logging.debug(f"Could not set the application icon: {e}")

DEFAULT_SEARCH_ROOTS = [
    r"Z:\LeonK\Lit_immob",
    r"Z:\LeonK\25_degrees_npr-1_vs_rde4",
    r"Z:\LeonK\20_degrees_N2",
    r"Z:\LeonK\25_degrees_N2_vs_rde4",
    r"Z:\neurobiology\zimmer\LeonK\Lit_immob",
    r"Z:\neurobiology\zimmer\LeonK\25_degrees_npr-1_vs_rde4",
]

DARK_THEME_QSS = """
QDialog {
    background-color: #1e2227;
    color: #abb2bf;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 12pt;
}
QLabel {
    color: #abb2bf;
}
QLineEdit {
    background-color: #282c34;
    border: 1px solid #3e4451;
    border-radius: 6px;
    padding: 6px 12px;
    color: #ffffff;
    font-size: 12pt;
}
QLineEdit:focus {
    border: 1px solid #61afef;
}
QPushButton {
    background-color: #2c313a;
    border: 1px solid #3e4451;
    border-radius: 6px;
    padding: 5px 14px;
    color: #dcdfe4;
    font-weight: 500;
    font-size: 12pt;
}
QPushButton:hover {
    background-color: #353b45;
    border-color: #528bff;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #21252b;
}
QPushButton#chipButton {
    background-color: #21252b;
    border: 1px solid #3e4451;
    border-radius: 12px;
    padding: 3px 12px;
    font-size: 11pt;
    color: #abb2bf;
}
QPushButton#chipButton:hover {
    border-color: #61afef;
    color: #ffffff;
}
QPushButton#chipButton:checked {
    background-color: #2c3e50;
    border-color: #61afef;
    color: #61afef;
    font-weight: bold;
}
QPushButton#launchButton {
    background-color: #2e7d32;
    border: 1px solid #388e3c;
    color: #ffffff;
    font-size: 13pt;
    font-weight: bold;
    padding: 8px 22px;
    border-radius: 6px;
}
QPushButton#launchButton:hover {
    background-color: #388e3c;
    border-color: #4caf50;
}
QPushButton#launchButton:disabled {
    background-color: #2c313a;
    border-color: #3e4451;
    color: #5c6370;
}
QPushButton#actionButton {
    background-color: #2c313a;
    border: 1px solid #3e4451;
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 11pt;
    color: #dcdfe4;
}
QPushButton#actionButton:hover {
    background-color: #3e4451;
    border-color: #61afef;
}
QTableWidget {
    background-color: #21252b;
    alternate-background-color: #242830;
    border: 1px solid #3e4451;
    border-radius: 6px;
    gridline-color: #2c313a;
    color: #abb2bf;
    selection-background-color: #3e4451;
    selection-color: #ffffff;
}
QTableWidget::item {
    padding: 3px 6px;
}
QTableWidget::item:selected {
    background-color: #2c3e50;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #1a1d23;
    color: #98c379;
    padding: 5px 8px;
    border: 1px solid #282c34;
    font-weight: bold;
    font-size: 12pt;
}
QMenu {
    background-color: #21252b;
    color: #abb2bf;
    border: 1px solid #3e4451;
    border-radius: 6px;
    padding: 4px 0;
}
QMenu::item {
    padding: 6px 24px;
}
QMenu::item:selected {
    background-color: #2c3e50;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #3e4451;
    margin: 4px 8px;
}
QCheckBox {
    color: #abb2bf;
    spacing: 6px;
    font-size: 12pt;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #4b5263;
    border-radius: 4px;
    background-color: #282c34;
}
QCheckBox::indicator:hover {
    border-color: #61afef;
}
QCheckBox::indicator:checked {
    background-color: #61afef;
    border-color: #61afef;
}
QProgressBar {
    border: 1px solid #3e4451;
    border-radius: 4px;
    background-color: #21252b;
    text-align: center;
    color: #abb2bf;
    height: 14px;
    font-size: 10pt;
}
QProgressBar::chunk {
    background-color: #61afef;
    border-radius: 3px;
}
QFrame#cardFrame {
    background-color: #21252b;
    border: 1px solid #3e4451;
    border-radius: 8px;
    padding: 6px;
}
QFrame#inspectorFrame {
    background-color: #1a1d23;
    border: 1px solid #3e4451;
    border-radius: 8px;
    padding: 8px;
}
QSplitter::handle {
    background-color: #282c34;
    width: 4px;
}
QSplitter::handle:hover {
    background-color: #61afef;
}
QPushButton#badgeChip {
    background-color: #21352a;
    color: #98c379;
    border: 1px solid #2e5538;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11pt;
    font-weight: bold;
    min-height: 18px;
}
QPushButton#badgeChip:hover {
    background-color: #2c4a3b;
    border-color: #98c379;
    color: #ffffff;
}
QPushButton#quickGlanceButton {
    background-color: #1e3148;
    color: #61afef;
    border: 1px solid #2d4f7c;
    border-radius: 5px;
    padding: 5px 12px;
    font-size: 11pt;
    font-weight: bold;
}
QPushButton#quickGlanceButton:hover {
    background-color: #264263;
    border-color: #61afef;
    color: #ffffff;
}
QPushButton#quickGlanceButton:disabled {
    background-color: #1e2227;
    color: #5c6370;
    border-color: #282c34;
}
"""

# ==============================================================================
# Canonical Path & File Fingerprinting
# ==============================================================================

@functools.lru_cache(maxsize=4096)
def resolve_existing_path(p: str) -> str:
    """If path does not exist, check alternative network share mounts (Z:\\ vs Z:\\neurobiology\\zimmer).

    Touches the filesystem (network stats on Z:), so it is cached and must only be called for
    scan roots / launch targets, from the worker thread where possible. Never call it from
    ``canonical_path``, which runs per-row on the UI thread.
    """
    if not p:
        return p
    try:
        if os.path.exists(p):
            return p
    except Exception:
        pass
    p_norm = os.path.normpath(p)
    if p_norm.lower().startswith("z:\\neurobiology\\zimmer"):
        alt = "Z:" + p_norm[len("z:\\neurobiology\\zimmer"):]
        try:
            if os.path.exists(alt):
                return alt
        except Exception:
            pass
    elif p_norm.lower().startswith("z:\\"):
        alt = "Z:\\neurobiology\\zimmer" + p_norm[2:]
        try:
            if os.path.exists(alt):
                return alt
        except Exception:
            pass
    return p


def canonical_path(p: Optional[str]) -> str:
    """
    Returns a normalized, canonical absolute path representation.
    Ensures consistent forward/backslash handling, drive letter casing on Windows,
    and trailing slash stripping so paths compare identically in sets and dicts.
    Pure string manipulation: no filesystem access (see ``resolve_existing_path``).
    """
    if not p:
        return ""
    norm = os.path.normpath(os.path.abspath(p))
    if len(norm) >= 2 and norm[1] == ":" and norm[0].isalpha():
        norm = norm[0].upper() + norm[1:]
    return norm


def is_drive_root(p: str) -> bool:
    """'C:\\' (scanning a whole drive because one recent project sits directly on it is never intended)"""
    return os.path.splitdrive(p)[1] in ("", "\\", "/")


REFERENCE_SOURCE = "Reference"
OWN_SOURCE = "Mine"
REFERENCE_PATTERNS_ENV = "WBFM_REFERENCE_PATTERNS"


def reference_patterns() -> List[str]:
    """
    Lower-case substrings that mark a recording as an annotated reference recording (to compare your own
    recordings against). Configured per machine via the WBFM_REFERENCE_PATTERNS environment variable,
    ';'-separated, e.g. in launcher_settings.local.bat:  SET "WBFM_REFERENCE_PATTERNS=reference_set;Z:\\refs"
    """
    raw = os.environ.get(REFERENCE_PATTERNS_ENV, "")
    return [p.strip().lower() for p in raw.split(";") if p.strip()]


def recording_source(rec: dict, patterns: Optional[List[str]] = None) -> str:
    """REFERENCE_SOURCE if the recording's path or name contains a reference pattern, otherwise OWN_SOURCE"""
    if patterns is None:
        patterns = reference_patterns()
    haystack = f"{rec.get('path', '')} {rec.get('name', '')}".lower()
    return REFERENCE_SOURCE if any(p in haystack for p in patterns) else OWN_SOURCE


def reference_patterns_hint() -> str:
    patterns = reference_patterns()
    if patterns:
        return f"Reference recordings are those whose path or name contains: {', '.join(patterns)}"
    return (f"No reference recordings configured: set {REFERENCE_PATTERNS_ENV} (';'-separated parts of "
            f"folder names/paths) in launcher_settings.local.bat")


def clean_strain(strain: str) -> str:
    """Folder names that start with a date used to yield strains like '2026'; those are not strains"""
    strain = strain or ""
    return "" if strain.isdigit() else strain


NEURON_QUERY_PREFIXES = ("n:", "neuron:", "neurons:")


def parse_neuron_query(text: str) -> Optional[List[str]]:
    """'n:AVAL, RIML?' -> ['aval', 'riml'] (lower case, '?' stripped); None if this isn't a neuron query"""
    text = (text or "").strip()
    for prefix in NEURON_QUERY_PREFIXES:
        if text.lower().startswith(prefix):
            names = [n.replace("?", "").strip().lower() for n in text[len(prefix):].split(",")]
            return [n for n in names if n]
    return None


def confident_neuron_names(rec: dict) -> set:
    """Lower-case names that are annotated without a '?' (the ones usable as a reference)"""
    return {str(n).lower() for n in rec.get("annotated_names", []) if n and "?" not in str(n)}


def count_neuron_matches(rec: dict, wanted: List[str]) -> int:
    have = confident_neuron_names(rec)
    return sum(1 for n in wanted if n in have)


def read_exposure_time(config_path: str) -> Optional[float]:
    """
    physical_units.exposure_time (ms) from project_config.yaml

    The exposure time sets the volume rate (20 ms ~ 2.1 vol/s, 12 ms ~ 3.5 vol/s), so recordings with the same value
    have the same time resolution and can be compared directly. Reads only the small yaml file.
    """
    try:
        import yaml
        if os.path.isdir(config_path):
            config_path = os.path.join(config_path, "project_config.yaml")
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        value = (cfg.get("physical_units") or {}).get("exposure_time")
        return float(value) if value is not None else None
    except Exception:
        return None


def acquisition_similarity(target: dict, rec: dict) -> tuple:
    """Sort key: same exposure time (same frame rate) first, then the closest number of volumes"""
    t_exp, r_exp = target.get("exposure_time"), rec.get("exposure_time")
    same_rate = t_exp is not None and t_exp == r_exp
    t_vol, r_vol = target.get("num_volumes"), rec.get("num_volumes")
    diff = float(abs(t_vol - r_vol)) if t_vol and r_vol else float("inf")
    return (0 if same_rate else 1, diff)


def is_comparable(target: dict, rec: dict, tolerance: float = 0.35) -> bool:
    """Same frame rate and a similar length (within ``tolerance`` of the target's number of volumes)"""
    same_rate, diff = acquisition_similarity(target, rec)
    t_vol = target.get("num_volumes")
    return same_rate == 0 and bool(t_vol) and diff <= tolerance * t_vol


def describe_acquisition(rec: dict) -> str:
    """'1001 vol · 20 ms'"""
    parts = []
    if rec.get("num_volumes"):
        parts.append(f"{rec['num_volumes']} vol")
    if rec.get("exposure_time") is not None:
        parts.append(f"{rec['exposure_time']:g} ms")
    return " · ".join(parts)


def get_project_fingerprint(project_dir: str) -> str:
    """
    Computes a composite fingerprint based on modification times and sizes of sentinel files.
    Fast check (a few stat calls) to detect when any pipeline step completes or manual annotations change.
    """
    parts = []
    norm_dir = canonical_path(project_dir)
    try:
        st = os.stat(norm_dir)
        parts.append(f"{st.st_mtime_ns}:{st.st_size}")
    except Exception:
        parts.append("0:0")

    sentinels = [
        "project_config.yaml",
        os.path.join("1-segmentation", "masks.zarr"),
        os.path.join("1-segmentation", "metadata.pickle"),
        os.path.join("3-tracking", "postprocessing", "combined_3d_tracks.h5"),
        os.path.join("4-traces", "green_traces.h5"),
        os.path.join("3-tracking", "barlow_tracker", "worm_tracker_barlow.pickle"),
        os.path.join("3-tracking", "manual_annotation", "manual_annotation.xlsx"),
        os.path.join("3-tracking", "manual_annotation", "manual_annotation.h5"),
        os.path.join("3-tracking", "manual_annotation", "manual_annotation_iterative.xlsx"),
        os.path.join("3-tracking", "manual_annotation", "manual_annotation_hungarian.xlsx"),
        os.path.join("3-tracking", "id_transfer_output", "hungarian", "manual_annotation.xlsx"),
        os.path.join("3-tracking", "hungarian", "manual_annotation.xlsx"),
        "manual_annotation.xlsx",
    ]

    for rel_path in sentinels:
        full_path = os.path.join(norm_dir, rel_path)
        try:
            st = os.stat(full_path)
            parts.append(f"{rel_path}:{st.st_mtime_ns}:{st.st_size}")
        except Exception:
            parts.append(f"{rel_path}:0:0")

    import hashlib
    return hashlib.md5(";".join(parts).encode("utf-8")).hexdigest()


# ==============================================================================
# History & Directory Persistence
# ==============================================================================

def load_history() -> List[str]:
    """Loads recent project paths (list of strings for backward compatibility)."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                paths = []
                seen = set()
                for item in data:
                    raw_path = ""
                    if isinstance(item, str):
                        raw_path = item
                    elif isinstance(item, dict) and "path" in item:
                        raw_path = item["path"]
                    canon = canonical_path(raw_path)
                    if canon and canon not in seen:
                        seen.add(canon)
                        paths.append(raw_path)
                return paths
        except Exception:
            pass
    return []


def load_history_entries() -> List[Dict[str, Any]]:
    """Loads recent projects with timestamps and metadata, deduplicated by canonical path."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                entries = []
                seen = set()
                for item in data:
                    raw_path = ""
                    entry = {}
                    if isinstance(item, str):
                        raw_path = item
                        entry = {"path": item, "timestamp": None}
                    elif isinstance(item, dict) and "path" in item:
                        raw_path = item["path"]
                        entry = dict(item)
                    canon = canonical_path(raw_path)
                    if canon and canon not in seen:
                        seen.add(canon)
                        entries.append(entry)
                return entries
        except Exception:
            pass
    return []


def save_history(project_path: str):
    """Saves project path to history with ISO timestamp, deduplicated by canonical path."""
    entries = load_history_entries()
    norm = canonical_path(project_path)
    entries = [e for e in entries if canonical_path(e.get("path", "")) != norm]
    new_entry = {
        "path": project_path,
        "name": os.path.basename(os.path.dirname(norm)) if norm.lower().endswith(".yaml") else os.path.basename(norm),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    entries.insert(0, new_entry)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries[:30], f, indent=2)
    except Exception as e:
        logging.warning(f"Could not save history to {HISTORY_FILE}: {e}")


def load_custom_roots() -> List[str]:
    """Loads user-added custom search roots, deduplicated by canonical path."""
    if os.path.exists(CUSTOM_ROOTS_FILE):
        try:
            with open(CUSTOM_ROOTS_FILE, "r", encoding="utf-8") as f:
                roots = json.load(f)
                if isinstance(roots, list):
                    seen = set()
                    cleaned = []
                    for r in roots:
                        if isinstance(r, str):
                            cr = canonical_path(r)
                            if cr and cr not in seen:
                                seen.add(cr)
                                cleaned.append(r)
                    return cleaned
        except Exception:
            pass
    return []


def save_custom_roots(roots: List[str]):
    """Saves user-added custom search roots, deduplicated by canonical path."""
    try:
        seen = set()
        cleaned = []
        for r in roots:
            cr = canonical_path(r)
            if cr and cr not in seen:
                seen.add(cr)
                cleaned.append(r)
        with open(CUSTOM_ROOTS_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2)
    except Exception as e:
        logging.warning(f"Could not save custom roots: {e}")


def load_metadata_cache() -> Dict[str, Any]:
    """Loads cached project metadata with fingerprints and schema validation."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Filter out stale cache entries from previous schema versions and deduplicate keys
                    cleaned = {}
                    for k, v in data.items():
                        if (
                            isinstance(v, dict)
                            and "metadata" in v
                            and isinstance(v["metadata"], dict)
                            and "annotated_names" in v["metadata"]
                            and "annotated_details" in v["metadata"]
                        ):
                            canon_k = canonical_path(k)
                            v["metadata"]["path"] = canonical_path(v["metadata"].get("path", canon_k))
                            if "config_path" in v["metadata"]:
                                v["metadata"]["config_path"] = canonical_path(v["metadata"]["config_path"])
                            cleaned[canon_k] = v
                    return cleaned
        except Exception:
            pass
    return {}


def save_metadata_cache(cache: Dict[str, Any]):
    """Saves project metadata cache to file with canonicalized keys."""
    try:
        cleaned = {}
        for k, v in cache.items():
            cleaned[canonical_path(k)] = v
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2)
    except Exception as e:
        logging.warning(f"Could not save metadata cache: {e}")



# ==============================================================================
# Metadata Extraction
# ==============================================================================

def extract_metadata_for_project(project_dir: str, cache: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safely inspects a project directory and extracts status badges, neuron counts,
    volume counts, and annotated neuron identities without loading large arrays into memory.
    Leverages composite sentinel fingerprint and mtime-checked local caching for near-instant execution.
    """
    project_dir = canonical_path(project_dir)
    current_fp = get_project_fingerprint(project_dir)
    try:
        current_mtime = os.path.getmtime(project_dir)
    except Exception:
        current_mtime = 0

    # Return cached record if fingerprint matches and required schema keys exist
    if cache is not None and project_dir in cache:
        cached = cache[project_dir]
        cached_fp = cached.get("fingerprint")
        # An entry from a failed read is reused only briefly: transient problems (file being written, SMB hiccup,
        # Excel lock) heal on a later scan, and a permanently broken file is re-read at most every few minutes
        retry_due = bool(cached.get("read_errors")) and (
            time.time() - float(cached.get("checked_at", 0)) > INCOMPLETE_CACHE_RETRY_S)
        if (
            not retry_due
            and (cached_fp == current_fp if cached_fp else cached.get("mtime") == current_mtime)
            and "metadata" in cached
            and isinstance(cached["metadata"], dict)
            and "annotated_names" in cached["metadata"]
            and "annotated_details" in cached["metadata"]
        ):
            cached["metadata"]["path"] = canonical_path(cached["metadata"].get("path", project_dir))
            if "config_path" in cached["metadata"]:
                cached["metadata"]["config_path"] = canonical_path(cached["metadata"]["config_path"])
            if "exposure_time" not in cached["metadata"]:
                cached["metadata"]["exposure_time"] = read_exposure_time(
                    cached["metadata"].get("config_path") or project_dir)
            if "question_mark_count" not in cached["metadata"]:
                qm = [d for d in cached["metadata"].get("annotated_details", []) if d.get("is_question_mark") or "?" in d.get("id1", "") or "?" in d.get("id2", "")]
                cached["metadata"]["question_mark_count"] = len(qm)
                cached["metadata"]["has_question_marks"] = len(qm) > 0
                cached["metadata"]["question_mark_names"] = sorted(list({d.get("id1") for d in qm if d.get("id1")}))
            return cached["metadata"]

    cfg_candidate = canonical_path(os.path.join(project_dir, "project_config.yaml"))
    name = os.path.basename(project_dir)
    meta = {
        "name": name,
        "path": project_dir,
        "config_path": cfg_candidate if os.path.exists(cfg_candidate) else project_dir,
        "date": "",
        "strain": "",
        "num_volumes": None,
        "exposure_time": None,
        "has_masks": False,
        "has_tracks": False,
        "has_traces": False,
        "has_barlow": False,
        "tracked_count": None,
        "annotated_count": 0,
        "annotated_total": 0,
        "question_mark_count": 0,
        "has_question_marks": False,
        "question_mark_names": [],
        "annotated_names": [],
        "annotated_details": [],
        "is_fully_processed": False,
        "missing_annotations": False,
        "is_recent": False,
        "excel_path": None,
    }

    meta["exposure_time"] = read_exposure_time(cfg_candidate)

    # Parse Strain and Date from folder name
    strain_m = re.search(r"(AX\d+|ZIM\d+|N2)", name, re.IGNORECASE)
    if strain_m:
        meta["strain"] = strain_m.group(1).upper()
    else:
        parts = name.split("-")[0].split("_")
        meta["strain"] = clean_strain(parts[0] if parts else "")

    date_m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if date_m:
        meta["date"] = date_m.group(1)
    else:
        try:
            meta["date"] = datetime.datetime.fromtimestamp(current_mtime).strftime("%Y-%m-%d")
        except Exception:
            meta["date"] = ""

    # Check Pipeline Status Badges
    try:
        masks_zarr = os.path.join(project_dir, "1-segmentation", "masks.zarr")
        meta_pickle = os.path.join(project_dir, "1-segmentation", "metadata.pickle")
        meta["has_masks"] = os.path.exists(masks_zarr) or os.path.exists(meta_pickle)
    except Exception:
        pass

    tracks_h5 = os.path.join(project_dir, "3-tracking", "postprocessing", "combined_3d_tracks.h5")
    try:
        meta["has_tracks"] = os.path.exists(tracks_h5)
    except Exception:
        pass

    traces_h5 = os.path.join(project_dir, "4-traces", "green_traces.h5")
    try:
        meta["has_traces"] = os.path.exists(traces_h5)
    except Exception:
        pass

    barlow_pickle = os.path.join(project_dir, "3-tracking", "barlow_tracker", "worm_tracker_barlow.pickle")
    try:
        meta["has_barlow"] = os.path.exists(barlow_pickle)
    except Exception:
        pass

    # Reads that fail (h5 still being written, SMB hiccup, Excel lock) must not be cached as real results
    read_errors: List[str] = []

    # Total Tracked Neurons & Volumes (instant check via h5py headers)
    try:
        import h5py
        if meta["has_tracks"]:
            with h5py.File(tracks_h5, "r") as f:
                if "df_with_missing" in f:
                    grp = f["df_with_missing"]
                    if "block0_items_level0" in grp:
                        meta["tracked_count"] = len(grp["block0_items_level0"])
                    elif "axis0" in grp:
                        meta["tracked_count"] = len(grp["axis0"])
                    if "axis1" in grp:
                        meta["num_volumes"] = len(grp["axis1"])
        elif meta["has_traces"]:
            with h5py.File(traces_h5, "r") as f:
                if "df_with_missing" in f:
                    grp = f["df_with_missing"]
                    if "block0_items_level0" in grp:
                        meta["tracked_count"] = len(grp["block0_items_level0"])
                    elif "axis0" in grp:
                        meta["tracked_count"] = len(grp["axis0"])
                    if "axis1" in grp:
                        meta["num_volumes"] = len(grp["axis1"])
    except Exception as e:
        read_errors.append(f"tracks/traces: {e}")

    # ID'd Neurons Count & Annotated Identities: counts come from the newest annotation file, and "Open in Excel"
    # opens that same file (or its .xlsx twin when the newest is the .h5 copy); shared with `go check-ids`
    ann_target = newest_annotation_file(project_dir)
    excel_path = annotation_excel_file(project_dir, newest=ann_target)
    if excel_path:
        meta["excel_path"] = canonical_path(excel_path)

    if ann_target:
        try:
            import pandas as pd
            df = None
            if ann_target.endswith(".h5"):
                with pd.HDFStore(ann_target, mode="r") as store:
                    keys = store.keys()
                    df = store.select(keys[0]) if keys else pd.DataFrame()
            else:
                try:
                    df = pd.read_excel(ann_target)
                except PermissionError:
                    # Defensive fallback if locked by Microsoft Excel
                    try:
                        import tempfile
                        import shutil
                        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                            tmp_path = tmp.name
                        shutil.copy2(ann_target, tmp_path)
                        df = pd.read_excel(tmp_path)
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                    except Exception as lock_err:
                        logging.warning(f"Could not read locked Excel file {ann_target}: {lock_err}")
                        read_errors.append(f"annotations locked: {lock_err}")
                        df = pd.DataFrame()

            if df is not None and not df.empty:
                meta["annotated_total"] = len(df)
                cols = {str(c).strip().lower(): c for c in df.columns}
                id1_col = cols.get("id1") or cols.get("primary id") or cols.get("id 1")
                id2_col = cols.get("id2") or cols.get("alternative id") or cols.get("id 2")
                nid_col = cols.get("neuron id") or cols.get("neuron_id") or cols.get("track id") or cols.get("neuron")
                conf_col = cols.get("certainty") or cols.get("confidence") or cols.get("status")
                notes_col = cols.get("notes") or cols.get("comment") or cols.get("comments")

                annotated_names_set = set()
                annotated_details = []

                for idx, row in df.iterrows():
                    # Parse neuron/track id
                    if nid_col and pd.notna(row.get(nid_col)):
                        raw_nid = str(row[nid_col]).strip()
                        if raw_nid.isdigit():
                            track_id = f"neuron_{int(raw_nid):03d}"
                        elif raw_nid.lower() != "nan" and raw_nid:
                            track_id = raw_nid
                        else:
                            track_id = f"neuron_{idx:03d}"
                    else:
                        track_id = f"neuron_{idx:03d}"

                    # Parse ID1
                    id1 = ""
                    if id1_col and pd.notna(row.get(id1_col)):
                        v = str(row[id1_col]).strip()
                        if v.lower() not in ("nan", "none", ""):
                            id1 = v

                    # Parse ID2
                    id2 = ""
                    if id2_col and pd.notna(row.get(id2_col)):
                        v = str(row[id2_col]).strip()
                        if v.lower() not in ("nan", "none", ""):
                            id2 = v

                    # Parse Confidence / Certainty
                    conf = ""
                    if conf_col and pd.notna(row.get(conf_col)):
                        v = str(row[conf_col]).strip()
                        if v.lower() not in ("nan", "none", ""):
                            try:
                                f_val = float(v)
                                if f_val.is_integer():
                                    v = str(int(f_val))
                            except Exception:
                                pass
                            conf = v

                    # Parse Notes / Comment
                    notes = ""
                    if notes_col and pd.notna(row.get(notes_col)):
                        v = str(row[notes_col]).strip()
                        if v.lower() not in ("nan", "none", ""):
                            notes = v

                    has_qm = ("?" in id1) or ("?" in id2)
                    if id1 or id2:
                        if id1:
                            annotated_names_set.add(id1)
                        if id2:
                            annotated_names_set.add(id2)
                        annotated_details.append({
                            "track_id": track_id,
                            "id1": id1,
                            "id2": id2,
                            "confidence": conf,
                            "certainty": conf,
                            "comment": notes,
                            "notes": notes,
                            "is_question_mark": has_qm,
                        })

                meta["annotated_names"] = sorted(list(annotated_names_set))
                meta["annotated_details"] = annotated_details
                meta["annotated_count"] = len(annotated_details)

                qm_details = [d for d in annotated_details if d.get("is_question_mark")]
                meta["question_mark_count"] = len(qm_details)
                meta["has_question_marks"] = len(qm_details) > 0
                meta["question_mark_names"] = sorted(list({d.get("id1") for d in qm_details if d.get("id1")}))
        except Exception as e:
            logging.debug(f"Error reading annotations for {project_dir}: {e}")
            read_errors.append(f"annotations: {e}")

    meta["is_fully_processed"] = meta["has_masks"] and meta["has_tracks"] and meta["has_traces"]
    tc = meta["tracked_count"] or 0
    ac = meta["annotated_count"]
    meta["missing_annotations"] = (tc > 0 and (ac == 0 or ac < tc))

    # Update cache; results of failed reads are marked so they get retried (see INCOMPLETE_CACHE_RETRY_S)
    if cache is not None:
        entry = {"mtime": current_mtime, "fingerprint": current_fp, "metadata": meta}
        if read_errors:
            logging.debug(f"Incomplete metadata for {project_dir} (retried later): {read_errors}")
            entry.update(read_errors=read_errors, checked_at=time.time())
        cache[project_dir] = entry

    return meta


# ==============================================================================
# Asynchronous Background Scanner Worker
# ==============================================================================

class RecordingScannerWorker(QThread):
    """
    Background worker thread that discovers and parses recording directories
    across search roots without freezing the GUI.
    """
    recording_discovered = Signal(dict)
    recording_updated = Signal(dict)
    scan_progress = Signal(str, int, int)  # (status_message, current, total)
    scan_finished = Signal()

    def __init__(self, search_roots: List[str], recent_paths: List[str], bypass_cache: bool = False, parent=None):
        super().__init__(parent)
        self.search_roots = search_roots
        self.recent_paths = recent_paths
        self.bypass_cache = bypass_cache
        self._is_stopped = False
        self.cache: Dict[str, Any] = {}

    def stop(self):
        self._is_stopped = True
        self.requestInterruption()

    def run(self):
        # Parsing the cache canonicalises ~100 paths and reads ~1 MB: keep it off the UI thread
        if not self.bypass_cache:
            self.cache = load_metadata_cache()
        discovered_paths = set()
        projects_to_inspect = []

        # Prepare deduplicated canonical recent paths
        norm_recent_paths = []
        for p in self.recent_paths:
            if not p:
                continue
            cp = canonical_path(p)
            if cp and cp not in norm_recent_paths:
                norm_recent_paths.append(cp)

        # 1. First, yield recent paths immediately
        for p in norm_recent_paths:
            if self._is_stopped or self.isInterruptionRequested():
                return
            p_dir = canonical_path(os.path.dirname(p) if p.lower().endswith(".yaml") else p)
            if not p_dir or not os.path.exists(p_dir):
                continue
            if p_dir not in discovered_paths:
                discovered_paths.add(p_dir)
                name = os.path.basename(p_dir)
                date_m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
                date_str = date_m.group(1) if date_m else ""

                strain_m = re.search(r"(AX\d+|ZIM\d+|N2)", name, re.IGNORECASE)
                strain_str = strain_m.group(1).upper() if strain_m else clean_strain(name.split("-")[0].split("_")[0] if name else "")

                # If in cache, yield cached right away
                if (
                    not self.bypass_cache
                    and p_dir in self.cache
                    and "metadata" in self.cache[p_dir]
                    and "annotated_names" in self.cache[p_dir]["metadata"]
                ):
                    cached_meta = dict(self.cache[p_dir]["metadata"])
                    cached_meta["is_recent"] = True
                    self.recording_discovered.emit(cached_meta)
                else:
                    placeholder = {
                        "name": name,
                        "path": p_dir,
                        "config_path": p if p.lower().endswith(".yaml") else canonical_path(os.path.join(p_dir, "project_config.yaml")),
                        "date": date_str,
                        "strain": strain_str,
                        "num_volumes": None,
                        "has_masks": False,
                        "has_tracks": False,
                        "has_traces": False,
                        "has_barlow": False,
                        "tracked_count": None,
                        "annotated_count": 0,
                        "annotated_total": 0,
                        "question_mark_count": 0,
                        "has_question_marks": False,
                        "question_mark_names": [],
                        "annotated_names": [],
                        "annotated_details": [],
                        "is_fully_processed": False,
                        "missing_annotations": False,
                        "is_recent": True,
                    }
                    self.recording_discovered.emit(placeholder)
                projects_to_inspect.append(p_dir)

        # 2. Discover project directories in search roots (deduplicated)
        norm_roots = []
        for r in self.search_roots:
            # Mount-spelling resolution does network stats: done here, on the worker thread.
            cr = canonical_path(resolve_existing_path(canonical_path(r)))
            if cr and cr not in norm_roots:
                norm_roots.append(cr)

        for root in norm_roots:
            if self._is_stopped or self.isInterruptionRequested():
                return
            self.scan_progress.emit(f"Scanning {os.path.basename(root)}...", len(projects_to_inspect), 0)

            try:
                if not os.path.exists(root):
                    continue
            except Exception:
                continue

            # Check if root itself is a project
            cfg_file = os.path.join(root, "project_config.yaml")
            try:
                if os.path.exists(cfg_file):
                    root_canon = canonical_path(root)
                    if root_canon not in discovered_paths:
                        discovered_paths.add(root_canon)
                        projects_to_inspect.append(root_canon)

                        name = os.path.basename(root_canon)
                        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
                        date_str = date_m.group(1) if date_m else ""

                        strain_m = re.search(r"(AX\d+|ZIM\d+|N2)", name, re.IGNORECASE)
                        strain_str = strain_m.group(1).upper() if strain_m else clean_strain(name.split("-")[0].split("_")[0] if name else "")

                        if (
                            not self.bypass_cache
                            and root_canon in self.cache
                            and "metadata" in self.cache[root_canon]
                            and "annotated_names" in self.cache[root_canon]["metadata"]
                        ):
                            self.recording_discovered.emit(self.cache[root_canon]["metadata"])
                        else:
                            self.recording_discovered.emit({
                                "name": name,
                                "path": root_canon,
                                "config_path": canonical_path(cfg_file),
                                "date": date_str,
                                "strain": strain_str,
                                "num_volumes": None,
                                "has_masks": False,
                                "has_tracks": False,
                                "has_traces": False,
                                "has_barlow": False,
                                "tracked_count": None,
                                "annotated_count": 0,
                                "annotated_total": 0,
                                "question_mark_count": 0,
                                "has_question_marks": False,
                                "question_mark_names": [],
                                "annotated_names": [],
                                "annotated_details": [],
                                "is_fully_processed": False,
                                "missing_annotations": False,
                                "is_recent": False,
                            })
                    continue
            except Exception:
                pass

            # Shallow listing of immediate subdirectories
            try:
                subdirs = [d for d in os.listdir(root)]
            except Exception as e:
                logging.debug(f"Could not list directory {root}: {e}")
                continue

            for sub in subdirs:
                if self._is_stopped or self.isInterruptionRequested():
                    return
                full_sub = canonical_path(os.path.join(root, sub))
                try:
                    if full_sub in discovered_paths:
                        continue
                    if not os.path.isdir(full_sub):
                        continue
                    cfg_candidate = os.path.join(full_sub, "project_config.yaml")
                    if os.path.exists(cfg_candidate):
                        discovered_paths.add(full_sub)
                        projects_to_inspect.append(full_sub)

                        name = sub
                        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
                        date_str = date_m.group(1) if date_m else ""

                        strain_m = re.search(r"(AX\d+|ZIM\d+|N2)", name, re.IGNORECASE)
                        strain_str = strain_m.group(1).upper() if strain_m else clean_strain(name.split("-")[0].split("_")[0] if name else "")

                        # If in cache, emit cached info immediately
                        if (
                            not self.bypass_cache
                            and full_sub in self.cache
                            and "metadata" in self.cache[full_sub]
                            and "annotated_names" in self.cache[full_sub]["metadata"]
                        ):
                            self.recording_discovered.emit(self.cache[full_sub]["metadata"])
                        else:
                            self.recording_discovered.emit({
                                "name": name,
                                "path": full_sub,
                                "config_path": canonical_path(cfg_candidate),
                                "date": date_str,
                                "strain": strain_str,
                                "num_volumes": None,
                                "has_masks": False,
                                "has_tracks": False,
                                "has_traces": False,
                                "has_barlow": False,
                                "tracked_count": None,
                                "annotated_count": 0,
                                "annotated_total": 0,
                                "question_mark_count": 0,
                                "has_question_marks": False,
                                "question_mark_names": [],
                                "annotated_names": [],
                                "annotated_details": [],
                                "is_fully_processed": False,
                                "missing_annotations": False,
                                "is_recent": False,
                            })
                except Exception:
                    pass

        # 3. Deep metadata inspection for each project
        total = len(projects_to_inspect)
        recent_cfg_set = {p for p in norm_recent_paths}
        recent_dir_set = {canonical_path(os.path.dirname(p) if p.lower().endswith(".yaml") else p) for p in norm_recent_paths}

        for idx, project_dir in enumerate(projects_to_inspect, start=1):
            if self._is_stopped or self.isInterruptionRequested():
                return
            self.scan_progress.emit(f"Inspecting {os.path.basename(project_dir)}...", idx, total)
            try:
                meta = extract_metadata_for_project(project_dir, cache=self.cache)
                norm_p = canonical_path(meta["config_path"])
                meta["is_recent"] = (norm_p in recent_cfg_set) or (project_dir in recent_dir_set)
                self.recording_updated.emit(meta)
            except Exception as e:
                logging.debug(f"Error inspecting {project_dir}: {e}")

        # Save cache
        save_metadata_cache(self.cache)

        self.scan_progress.emit("Scan complete", total, total)
        self.scan_finished.emit()


# ==============================================================================
# Custom Table Item for Numeric / Boolean Sorting
# ==============================================================================

class SortableTableWidgetItem(QTableWidgetItem):
    """Custom table widget item supporting type-safe numeric and date sorting."""
    def __init__(self, text: str, sort_key: Any = None):
        super().__init__(text)
        self.sort_key = sort_key if sort_key is not None else text

    def __lt__(self, other):
        if isinstance(other, SortableTableWidgetItem):
            if isinstance(self.sort_key, type(other.sort_key)):
                return self.sort_key < other.sort_key
            try:
                return float(self.sort_key) < float(other.sort_key)
            except (ValueError, TypeError):
                return str(self.sort_key) < str(other.sort_key)
        return super().__lt__(other)


# ==============================================================================
# Qt Flow Layout (Wrapping horizontal chip badge layout)
# ==============================================================================

class FlowLayout(QLayout):
    """
    Standard Qt FlowLayout that lays out child widgets horizontally and
    wraps them into new lines when available width is exceeded.
    """
    def __init__(self, parent=None, margin: int = 0, spacing: int = -1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing if spacing >= 0 else 4)
        self._item_list = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self) -> int:
        return len(self._item_list)

    def itemAt(self, index: int):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), apply_geometry=False)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, apply_geometry=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, apply_geometry: bool = True) -> int:
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._item_list:
            widget = item.widget()
            if widget is not None and not widget.isVisibleTo(widget.parent()):
                continue
            item_size = item.sizeHint()
            space_x = spacing
            space_y = spacing
            next_x = x + item_size.width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item_size.width() + space_x
                line_height = 0

            if apply_geometry:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + margins.bottom()


# ==============================================================================
# Bilateral Pair Analysis Helper
# ==============================================================================

def compute_bilateral_stats(names: List[str]) -> Tuple[int, int]:
    """
    Counts bilateral pairs (e.g., AVAL and AVAR) and unpaired identities
    from a list of neuron names following standard C. elegans nomenclature.

    Returns:
        Tuple[int, int]: (number_of_bilateral_pairs, number_of_unpaired_neurons)
    """
    if not names:
        return 0, 0
    name_set = set(names)
    pairs = set()
    paired_names = set()
    for n in name_set:
        if len(n) >= 2:
            if n.endswith("L") and (n[:-1] + "R") in name_set:
                pairs.add(n[:-1])
                paired_names.add(n)
                paired_names.add(n[:-1] + "R")
            elif n.endswith("R") and (n[:-1] + "L") in name_set:
                pairs.add(n[:-1])
                paired_names.add(n)
                paired_names.add(n[:-1] + "L")
    num_pairs = len(pairs)
    unpaired = len(name_set) - len(paired_names)
    return num_pairs, unpaired


# ==============================================================================
# Quick-Glance Neuron Annotation Inspector Dialog
# ==============================================================================

class QuickGlanceAnnotationDialog(QDialog):
    """
    Dedicated modal dialog providing a fast, interactive 'quick glance'
    inspection of all annotated neurons for a recording.

    Features:
      - Searchable table: Neuron #, Primary ID, Alternative ID, Confidence, Notes
      - Real-time instant substring filter
      - Summary header: Total Annotated: X / Y tracked neurons (Z%) | Unique Classes: N
      - Quick export: '📋 Copy ID List' (to system clipboard)
      - Quick open: '📂 Open manual_annotation.xlsx' in default application
    """
    def __init__(self, record: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None, filter_text: str = ""):
        super().__init__(parent)
        self.record = record or {}
        rec_name = self.record.get("name", "Recording")
        self.setWindowTitle(f"Annotated Neurons — {rec_name}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(640, 420)
        self.resize(760, 520)
        self.setStyleSheet(DARK_THEME_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Summary Header Card
        header_card = QFrame()
        header_card.setObjectName("cardFrame")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(4)

        title_lbl = QLabel(f"Recording: {rec_name}")
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title_lbl.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(title_lbl)

        self.lbl_summary = QLabel(self._build_summary_text())
        self.lbl_summary.setStyleSheet("color: #56b6c2; font-size: 11pt; font-weight: 500;")
        header_layout.addWidget(self.lbl_summary)
        layout.addWidget(header_card)

        # 2. Filter Bar
        filter_box = QHBoxLayout()
        filter_box.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by neuron (e.g. AVA, RMD, SMD, PVP, neuron_001)...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_filter)
        filter_box.addWidget(self.search_input)

        details = self.record.get("annotated_details", [])
        self.lbl_filter_count = QLabel(f"Showing {len(details)} of {len(details)}")
        self.lbl_filter_count.setStyleSheet("color: #7f848e; font-size: 11pt;")
        filter_box.addWidget(self.lbl_filter_count)

        qm_count = self.record.get("question_mark_count", 0)
        self.btn_toggle_qm = QPushButton(f"⚠️ Show '?' Only ({qm_count})")
        self.btn_toggle_qm.setObjectName("actionButton")
        self.btn_toggle_qm.setCheckable(True)
        if qm_count > 0:
            self.btn_toggle_qm.setStyleSheet("""
                QPushButton {
                    background-color: #3d311c;
                    color: #e5c07b;
                    border: 1px solid #9e7a3b;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #e5c07b;
                    color: #1e2227;
                    border: 1px solid #ffd580;
                }
            """)
            self.btn_toggle_qm.setToolTip("Show only uncertain '?' neurons transferred from ID pipeline")
        else:
            self.btn_toggle_qm.setEnabled(False)
            self.btn_toggle_qm.setToolTip("No uncertain '?' neurons in this recording")
        self.btn_toggle_qm.toggled.connect(self._apply_filter)
        filter_box.addWidget(self.btn_toggle_qm)

        layout.addLayout(filter_box)

        # 3. Clean Searchable Table
        self.columns = ["Neuron #", "Primary ID", "Alternative ID", "Confidence / Status", "Notes"]
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table)

        # Populate rows
        self._populate_table(details)

        # 4. Bottom Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_copy_ids = QPushButton("📋 Copy ID List")
        self.btn_copy_ids.setObjectName("actionButton")
        self.btn_copy_ids.setToolTip("Copy comma-separated list of identified neurons to clipboard")
        self.btn_copy_ids.clicked.connect(self._copy_id_list)
        btn_layout.addWidget(self.btn_copy_ids)

        self.btn_copy_qm = QPushButton("📋 Copy '?' List")
        self.btn_copy_qm.setObjectName("actionButton")
        self.btn_copy_qm.setEnabled(qm_count > 0)
        self.btn_copy_qm.setToolTip("Copy comma-separated list of unconfirmed '?' neurons to clipboard")
        self.btn_copy_qm.clicked.connect(self._copy_qm_list)
        btn_layout.addWidget(self.btn_copy_qm)

        self.btn_open_excel = QPushButton("📂 Open manual_annotation.xlsx")
        self.btn_open_excel.setObjectName("actionButton")
        excel_path = self.record.get("excel_path")
        has_excel = bool(excel_path and os.path.exists(excel_path))
        self.btn_open_excel.setEnabled(has_excel)
        self.btn_open_excel.setToolTip("Open manual annotation spreadsheet in system editor" if has_excel else "Excel file not found on disk")
        self.btn_open_excel.clicked.connect(self._open_excel)
        btn_layout.addWidget(self.btn_open_excel)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        if filter_text:
            if filter_text == "?":
                self.btn_toggle_qm.setChecked(True)
            else:
                self.search_input.setText(filter_text)

    def _build_summary_text(self) -> str:
        details = self.record.get("annotated_details", [])
        names = self.record.get("annotated_names", [])
        ac = self.record.get("annotated_count")
        if ac is None:
            ac = len(details)
        tc = self.record.get("tracked_count") or self.record.get("annotated_total", 0) or len(details)
        pct = (ac / tc * 100) if tc > 0 else 0.0
        classes = {n[:-1] if (n.endswith(('L', 'R')) and len(n) > 2) else n for n in names}
        qm_count = self.record.get("question_mark_count", 0)
        qm_str = f" | Pending '?' Review: {qm_count}" if qm_count > 0 else ""
        return f"Total Annotated: {ac} / {tc} tracked neurons ({pct:.1f}%) | Unique Classes: {len(classes)}{qm_str}"

    def _populate_table(self, details: List[Dict[str, Any]]):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(details))
        for r, d in enumerate(details):
            track_id = d.get("track_id", f"neuron_{r:03d}")
            id1 = d.get("id1", "")
            id2 = d.get("id2", "")
            conf = str(d.get("confidence", "") or d.get("certainty", "") or "")
            notes = str(d.get("comment", "") or d.get("notes", "") or "")
            has_qm = bool(d.get("is_question_mark") or ("?" in id1) or ("?" in id2))

            m = re.search(r"(\d+)", track_id)
            t_sort = int(m.group(1)) if m else track_id
            item_track = SortableTableWidgetItem(track_id, sort_key=t_sort)
            item_track.setTextAlignment(Qt.AlignCenter)
            item_track.setFont(QFont("Consolas", 10))

            item_id1 = SortableTableWidgetItem(id1, sort_key=id1.lower())
            item_id1.setTextAlignment(Qt.AlignCenter)
            if id1:
                item_id1.setForeground(QColor("#e5c07b" if has_qm else "#98c379"))
                item_id1.setFont(QFont("Segoe UI", 10, QFont.Bold))
            else:
                item_id1.setForeground(QColor("#5c6370"))

            item_id2 = SortableTableWidgetItem(id2, sort_key=id2.lower())
            item_id2.setTextAlignment(Qt.AlignCenter)
            if id2:
                item_id2.setForeground(QColor("#e5c07b"))
            else:
                item_id2.setForeground(QColor("#5c6370"))

            item_conf = SortableTableWidgetItem(conf, sort_key=conf)
            item_conf.setTextAlignment(Qt.AlignCenter)
            item_conf.setForeground(QColor("#abb2bf"))

            item_notes = SortableTableWidgetItem(notes, sort_key=notes.lower())
            item_notes.setForeground(QColor("#abb2bf"))

            if has_qm:
                bg = QBrush(QColor("#2d2416"))
                item_track.setBackground(bg)
                item_id1.setBackground(bg)
                item_id2.setBackground(bg)
                item_conf.setBackground(bg)
                item_notes.setBackground(bg)
                item_id1.setToolTip("Unconfirmed '?' neuron from ID-transfer pipeline (needs manual review)")

            self.table.setItem(r, 0, item_track)
            self.table.setItem(r, 1, item_id1)
            self.table.setItem(r, 2, item_id2)
            self.table.setItem(r, 3, item_conf)
            self.table.setItem(r, 4, item_notes)

        self.table.setSortingEnabled(True)

    def _apply_filter(self):
        query = self.search_input.text().strip().lower()
        qm_only = hasattr(self, "btn_toggle_qm") and self.btn_toggle_qm.isChecked()
        visible_count = 0
        total_count = self.table.rowCount()
        for r in range(total_count):
            if qm_only:
                id1_text = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
                id2_text = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
                if "?" not in id1_text and "?" not in id2_text:
                    self.table.setRowHidden(r, True)
                    continue

            if not query:
                self.table.setRowHidden(r, False)
                visible_count += 1
                continue
            row_match = False
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item and query in item.text().lower():
                    row_match = True
                    break
            self.table.setRowHidden(r, not row_match)
            if row_match:
                visible_count += 1
        self.lbl_filter_count.setText(f"Showing {visible_count} of {total_count}")

    def _copy_id_list(self):
        names = self.record.get("annotated_names", [])
        if not names:
            details = self.record.get("annotated_details", [])
            names = sorted(list({d.get("id1") for d in details if d.get("id1")}))
        text = ", ".join(names)
        QApplication.clipboard().setText(text)
        old_text = self.btn_copy_ids.text()
        self.btn_copy_ids.setText("✓ Copied!")
        QTimer.singleShot(1500, lambda: self.btn_copy_ids.setText(old_text))

    def _copy_qm_list(self):
        qm_names = self.record.get("question_mark_names", [])
        if not qm_names:
            details = self.record.get("annotated_details", [])
            qm_names = sorted(list({d.get("id1") for d in details if d.get("is_question_mark") and d.get("id1")}))
        text = ", ".join(qm_names)
        QApplication.clipboard().setText(text)
        old_text = self.btn_copy_qm.text()
        self.btn_copy_qm.setText("✓ Copied '?' List!")
        QTimer.singleShot(1500, lambda: self.btn_copy_qm.setText(old_text))

    def _open_excel(self):
        excel_path = self.record.get("excel_path")
        if excel_path and os.path.exists(excel_path):
            try:
                os.startfile(excel_path)
            except Exception as e:
                QMessageBox.warning(self, "Open Error", f"Could not open file:\n{e}")

    def _show_context_menu(self, pos: QPoint):
        item = self.table.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        act_copy_cell = menu.addAction("Copy Cell")
        act_copy_id = menu.addAction("Copy Primary ID")
        act_copy_row = menu.addAction("Copy Row")
        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if not action:
            return

        r = item.row()
        if action == act_copy_cell:
            QApplication.clipboard().setText(item.text())
        elif action == act_copy_id:
            id_item = self.table.item(r, 1)
            if id_item:
                QApplication.clipboard().setText(id_item.text())
        elif action == act_copy_row:
            row_vals = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in range(self.table.columnCount())]
            QApplication.clipboard().setText("\t".join(row_vals))


# ==============================================================================
# Main Qt Dashboard & Launcher Dialog
# ==============================================================================

class WBFMRecordingDashboard(QDialog):
    """
    Modern Qt-based Recording Dashboard & Launcher for WBFM.
    """
    def __init__(self, standalone: bool = False, parent=None):
        super().__init__(parent)
        self.standalone = standalone
        self.setWindowTitle("WBFM Trace Explorer")
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinMaxButtonsHint
            | Qt.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setMinimumSize(720, 420)
        self.resize(1260, 720)
        self.setStyleSheet(DARK_THEME_QSS)

        self.selected_project_path: Optional[str] = None
        self.selected_record: Optional[Dict[str, Any]] = None
        self.running_processes: List[Tuple[Any, str]] = []

        self.records_by_path: Dict[str, Dict[str, Any]] = {}
        self.row_by_path: Dict[str, Any] = {}  # canonical path -> first-column QTableWidgetItem
        self._similarity_target: Optional[dict] = None  # recording whose acquisition the neuron search ranks by
        self.active_strain_filter: str = "All"
        self.detected_strains: set = set()

        # Load settings
        self.settings = QSettings("ZimmerLab", "WBFMTraceExplorer")
        saved_geometry = self.settings.value("geometry")
        if saved_geometry:
            self.restoreGeometry(saved_geometry)

        if self.settings.value("is_maximized", False, type=bool):
            self.showMaximized()

        saved_tracklets = self.settings.value("load_tracklets", False, type=bool)
        self.load_tracklets: bool = saved_tracklets

        # Search roots
        self.search_roots = [canonical_path(r) for r in DEFAULT_SEARCH_ROOTS]
        for cr in load_custom_roots():
            cr_norm = canonical_path(cr)
            if cr_norm and cr_norm not in self.search_roots:
                self.search_roots.append(cr_norm)

        # Recent projects
        self.recent_paths = [canonical_path(p) for p in load_history()]

        # Add parent directories of recent projects as candidate roots
        for rp in self.recent_paths:
            try:
                p_dir = canonical_path(os.path.dirname(rp) if rp.lower().endswith(".yaml") else rp)
                parent_dir = canonical_path(os.path.dirname(p_dir))
                # Existence is checked by the scanner worker; no network stat on the UI thread.
                if parent_dir and not is_drive_root(parent_dir) and parent_dir not in self.search_roots:
                    self.search_roots.append(parent_dir)
            except Exception:
                pass

        self._setup_ui()
        self._start_scanner()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 6)
        main_layout.setSpacing(6)

        # ----------------- Header Section -----------------
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("WBFM Recordings")
        title_font = QFont("Segoe UI", 11, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #dcdfe4;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.badge_count_label = QLabel("0 recordings")
        self.badge_count_label.setStyleSheet(
            "background-color: #21252b; color: #98c379; padding: 2px 8px; "
            "border-radius: 8px; font-weight: bold; border: 1px solid #3e4451; font-size: 10pt;"
        )
        header_layout.addWidget(self.badge_count_label)
        main_layout.addLayout(header_layout)

        # ----------------- Filter & Search Bar -----------------
        filter_frame = QFrame()
        filter_frame.setObjectName("cardFrame")
        filter_layout = QVBoxLayout(filter_frame)
        filter_layout.setContentsMargins(8, 6, 8, 6)
        filter_layout.setSpacing(6)

        # Search row
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter recordings (Ctrl+F)  •  find neurons: n:AVAL, RIML, AVAR")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_filters)
        search_row.addWidget(self.search_input, stretch=4)

        # Action buttons
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setToolTip("Re-scan directories (F5)")
        self.btn_refresh.clicked.connect(self._restart_scanner)
        search_row.addWidget(self.btn_refresh)

        self.btn_add_folder = QPushButton("Add Root...")
        self.btn_add_folder.setToolTip("Add search directory")
        self.btn_add_folder.clicked.connect(self._on_add_folder)
        search_row.addWidget(self.btn_add_folder)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setToolTip("Open project_config.yaml or folder")
        self.btn_browse.clicked.connect(self._on_browse_file)
        search_row.addWidget(self.btn_browse)

        filter_layout.addLayout(search_row)

        # Secondary row: Strain quick-filter chips & presets
        presets_row = QHBoxLayout()
        presets_row.setSpacing(10)

        # Strain Chips Container
        self.chips_layout = QHBoxLayout()
        self.chips_layout.setSpacing(5)
        presets_row.addLayout(self.chips_layout)
        self._rebuild_strain_chips()

        presets_row.addSpacing(10)

        # Presets Checkboxes
        self.chk_done_only = QCheckBox("✓ Done")
        self.chk_done_only.setToolTip("Show only recordings that are fully processed with all IDs confirmed (0 pending ?)")
        self.chk_done_only.stateChanged.connect(self._apply_filters)
        presets_row.addWidget(self.chk_done_only)

        self.chk_question_marks = QCheckBox("⚠️ Needs Review (?)")
        self.chk_question_marks.setToolTip("Show only recordings that have unconfirmed '?' neurons from ID-transfer")
        self.chk_question_marks.stateChanged.connect(self._apply_filters)
        presets_row.addWidget(self.chk_question_marks)

        self.chk_missing_annotations = QCheckBox("Missing IDs")
        self.chk_missing_annotations.setToolTip("Show recordings that are processed but missing neuron annotations")
        self.chk_missing_annotations.stateChanged.connect(self._apply_filters)
        presets_row.addWidget(self.chk_missing_annotations)

        self.chk_processed_only = QCheckBox("All Processed")
        self.chk_processed_only.stateChanged.connect(self._apply_filters)
        presets_row.addWidget(self.chk_processed_only)

        self.chk_recent_only = QCheckBox("Recent")
        self.chk_recent_only.stateChanged.connect(self._apply_filters)
        presets_row.addWidget(self.chk_recent_only)

        # Own vs. reference recordings (annotated recordings to compare against)
        self.source_combo = QComboBox()
        self.source_combo.addItems(["All sources", OWN_SOURCE, REFERENCE_SOURCE])
        self.source_combo.setToolTip("Show only your own recordings, or only the annotated reference recordings.\n"
                                     + reference_patterns_hint())
        self.source_combo.currentIndexChanged.connect(self._apply_filters)
        presets_row.addWidget(self.source_combo)

        presets_row.addStretch()
        filter_layout.addLayout(presets_row)

        main_layout.addWidget(filter_frame)

        # ----------------- Main Splitter: Table (Left) + Inspector (Right) -----------------
        self.splitter = QSplitter(Qt.Horizontal)

        # Left: Table
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget()
        self.columns = [
            "Recording", "Date", "Masks", "Tracks", "Traces", "Barlow",
            "Neurons", "Annotated"
        ]
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 58)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 68)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 58)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 58)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)

        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        table_layout.addWidget(self.table)
        self.splitter.addWidget(table_container)

        # Right: Inspector Sidebar Panel
        self.inspector_panel = self._create_inspector_panel()
        self.splitter.addWidget(self.inspector_panel)

        # Configure splitter behavior and stretch factors
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        # Set splitter sizes (table on left, inspector on right)
        saved_splitter = self.settings.value("splitter_state")
        if saved_splitter:
            self.splitter.restoreState(saved_splitter)
            sizes = self.splitter.sizes()
            if len(sizes) >= 2 and sizes[1] < 280:
                total_w = sum(sizes) if sum(sizes) > 0 else 1260
                insp_w = max(300, int(total_w * 0.28))
                self.splitter.setSizes([total_w - insp_w, insp_w])
        else:
            self.splitter.setSizes([880, 380])

        main_layout.addWidget(self.splitter, stretch=1)

        # ----------------- Launch Bar / Footer Section -----------------
        footer_frame = QFrame()
        footer_frame.setObjectName("cardFrame")
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(8, 4, 8, 4)
        footer_layout.setSpacing(4)

        action_row = QHBoxLayout()
        action_row.setSpacing(14)

        # Launch options checkboxes
        self.chk_fast_mode = QCheckBox("Fast Mode (Traces & IDs)")
        self.chk_fast_mode.setChecked(not self.load_tracklets)
        self.chk_fast_mode.setToolTip("Skips 3D tracklet meshes for fast launch")

        self.chk_full_tracklets = QCheckBox("Full Tracklets")
        self.chk_full_tracklets.setChecked(self.load_tracklets)
        self.chk_full_tracklets.setToolTip("Loads 3D tracklet meshes")

        # Mutual exclusivity for options
        self.chk_fast_mode.toggled.connect(self._on_fast_mode_toggled)
        self.chk_full_tracklets.toggled.connect(self._on_full_tracklets_toggled)

        action_row.addWidget(self.chk_fast_mode)
        action_row.addWidget(self.chk_full_tracklets)

        saved_keep_open = self.settings.value("keep_open", True, type=bool)
        self.chk_keep_open = QCheckBox("Keep open")
        self.chk_keep_open.setChecked(saved_keep_open)
        self.chk_keep_open.setToolTip("Keep dashboard open after launching Trace Explorer")
        if not self.standalone:
            self.chk_keep_open.setVisible(False)
        action_row.addWidget(self.chk_keep_open)

        action_row.addStretch()

        self.btn_cancel = QPushButton("Close")
        self.btn_cancel.clicked.connect(self.reject)
        action_row.addWidget(self.btn_cancel)

        self.btn_launch = QPushButton("Open Trace Explorer")
        self.btn_launch.setObjectName("launchButton")
        self.btn_launch.setEnabled(False)
        self.btn_launch.clicked.connect(self._on_launch_clicked)
        action_row.addWidget(self.btn_launch)

        footer_layout.addLayout(action_row)
        main_layout.addWidget(footer_frame)

        # ----------------- Status & Progress Bar -----------------
        status_row = QHBoxLayout()
        status_row.setContentsMargins(4, 0, 4, 0)
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #7f848e; font-size: 10pt;")
        status_row.addWidget(self.lbl_status, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        status_row.addWidget(self.progress_bar)

        main_layout.addLayout(status_row)

    def _create_inspector_panel(self) -> QWidget:
        """Constructs the right-hand Inspector Sidebar wrapped in a scroll area."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(280)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        panel = QFrame()
        panel.setObjectName("inspectorFrame")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Title / Header
        header_box = QHBoxLayout()
        insp_title = QLabel("Inspector")
        insp_title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        insp_title.setStyleSheet("color: #61afef;")
        header_box.addWidget(insp_title)
        header_box.addStretch()

        self.lbl_insp_strain = QLabel("")
        self.lbl_insp_strain.setStyleSheet(
            "background-color: #2c3e50; color: #61afef; padding: 2px 6px; "
            "border-radius: 10px; font-weight: bold; font-size: 10pt;"
        )
        self.lbl_insp_strain.setVisible(False)
        header_box.addWidget(self.lbl_insp_strain)
        layout.addLayout(header_box)

        # Name & Path
        self.lbl_insp_name = QLabel("No selection")
        self.lbl_insp_name.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_insp_name.setStyleSheet("color: #ffffff;")
        self.lbl_insp_name.setWordWrap(True)
        layout.addWidget(self.lbl_insp_name)

        self.lbl_insp_path = QLabel("")
        self.lbl_insp_path.setStyleSheet("color: #5c6370; font-size: 10.5pt;")
        self.lbl_insp_path.setWordWrap(True)
        layout.addWidget(self.lbl_insp_path)

        # Divider
        divider1 = QFrame()
        divider1.setFrameShape(QFrame.HLine)
        divider1.setStyleSheet("color: #2c313a;")
        layout.addWidget(divider1)

        # Acquisition & Volumes
        self.lbl_insp_acq = QLabel("Volumes: - | Date: -")
        self.lbl_insp_acq.setStyleSheet("color: #abb2bf; font-size: 11pt;")
        layout.addWidget(self.lbl_insp_acq)

        # Neurons & Annotation Progress
        ann_prog_header = QHBoxLayout()
        ann_title = QLabel("Annotation:")
        ann_title.setStyleSheet("color: #abb2bf; font-weight: bold; font-size: 11pt;")
        ann_prog_header.addWidget(ann_title)
        ann_prog_header.addStretch()
        self.lbl_insp_ann_stats = QLabel("0 / 0 (0.0%)")
        self.lbl_insp_ann_stats.setStyleSheet("color: #e5c07b; font-weight: bold; font-size: 11pt;")
        ann_prog_header.addWidget(self.lbl_insp_ann_stats)
        layout.addLayout(ann_prog_header)

        self.insp_progress = QProgressBar()
        self.insp_progress.setRange(0, 100)
        self.insp_progress.setValue(0)
        self.insp_progress.setFixedHeight(16)
        self.insp_progress.setTextVisible(True)
        layout.addWidget(self.insp_progress)

        # Unconfirmed '?' ID Alert Banner
        self.frame_qm_alert = QFrame()
        self.frame_qm_alert.setStyleSheet("""
            QFrame {
                background-color: #2b2214;
                border: 1px solid #7c5c28;
                border-radius: 6px;
                padding: 2px 4px;
            }
        """)
        qm_alert_layout = QHBoxLayout(self.frame_qm_alert)
        qm_alert_layout.setContentsMargins(6, 4, 6, 4)
        qm_alert_layout.setSpacing(6)

        self.lbl_qm_alert = QLabel("⚠️ 0 pending review (?)")
        self.lbl_qm_alert.setStyleSheet("color: #e5c07b; font-weight: bold; font-size: 10.5pt;")
        qm_alert_layout.addWidget(self.lbl_qm_alert, stretch=1)

        self.btn_qm_review = QPushButton("Review '?'")
        self.btn_qm_review.setObjectName("actionButton")
        self.btn_qm_review.setStyleSheet("""
            QPushButton {
                background-color: #3d311c;
                color: #e5c07b;
                border: 1px solid #9e7a3b;
                border-radius: 4px;
                padding: 2px 8px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #524225;
                color: #ffffff;
            }
        """)
        self.btn_qm_review.clicked.connect(lambda: self._open_quick_glance_dialog(filter_text="?"))
        qm_alert_layout.addWidget(self.btn_qm_review)
        layout.addWidget(self.frame_qm_alert)
        self.frame_qm_alert.setVisible(False)

        # Divider
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setStyleSheet("color: #2c313a;")
        layout.addWidget(divider2)

        # Annotated Identities Header & Quick Glance Section
        identities_header_row = QHBoxLayout()
        self.lbl_ann_identities_header = QLabel("Annotated Identities (0 unique)")
        self.lbl_ann_identities_header.setStyleSheet("color: #abb2bf; font-weight: bold; font-size: 11pt;")
        identities_header_row.addWidget(self.lbl_ann_identities_header)
        identities_header_row.addStretch()
        layout.addLayout(identities_header_row)

        # Bilateral Pair Summary
        self.lbl_bilateral_summary = QLabel("")
        self.lbl_bilateral_summary.setStyleSheet("color: #56b6c2; font-size: 11pt; font-style: italic;")
        layout.addWidget(self.lbl_bilateral_summary)

        # Prominent Full-Width Quick-Glance Button
        self.btn_quick_glance = QPushButton("🔍 View Annotated Neurons")
        self.btn_quick_glance.setObjectName("quickGlanceButton")
        self.btn_quick_glance.setEnabled(False)
        self.btn_quick_glance.setToolTip("Open full searchable neuron annotation viewer")
        self.btn_quick_glance.clicked.connect(self._on_quick_glance_clicked)
        layout.addWidget(self.btn_quick_glance)

        # Jump to the reference recordings that contain this recording's still-uncertain neurons
        self.btn_find_reference = QPushButton("🔎 Find reference recordings with these '?' neurons")
        self.btn_find_reference.setEnabled(False)
        self.btn_find_reference.setToolTip(
            "Filters the list to reference recordings that have this recording's '?' neurons annotated, "
            "best match first (same as typing n:NAME1, NAME2 in the search box).\n" + reference_patterns_hint())
        self.btn_find_reference.clicked.connect(self._on_find_reference_clicked)
        layout.addWidget(self.btn_find_reference)

        # Mini Filter
        self.ann_filter_input = QLineEdit()
        self.ann_filter_input.setPlaceholderText("Filter identities (e.g. AVA, SMD)...")
        self.ann_filter_input.setClearButtonEnabled(True)
        self.ann_filter_input.setStyleSheet(
            "background-color: #21252b; color: #abb2bf; border: 1px solid #3e4451; "
            "border-radius: 3px; padding: 2px 6px; font-size: 10pt;"
        )
        self.ann_filter_input.textChanged.connect(self._filter_sidebar_badges)
        layout.addWidget(self.ann_filter_input)

        # Interactive Badge Flow (Scrollable)
        self.ann_badges_scroll = QScrollArea()
        self.ann_badges_scroll.setWidgetResizable(True)
        self.ann_badges_scroll.setMinimumHeight(45)
        self.ann_badges_scroll.setMaximumHeight(130)
        self.ann_badges_scroll.setStyleSheet(
            "QScrollArea { background-color: #1a1d23; border: 1px solid #282c34; border-radius: 4px; }"
            "QWidget { background-color: #1a1d23; }"
        )

        self.ann_badges_container = QWidget()
        self.ann_badges_layout = FlowLayout(self.ann_badges_container, margin=4, spacing=4)
        self.ann_badges_scroll.setWidget(self.ann_badges_container)
        layout.addWidget(self.ann_badges_scroll)
        self.ann_badges: List[Tuple[str, QWidget]] = []

        # Divider
        divider3 = QFrame()
        divider3.setFrameShape(QFrame.HLine)
        divider3.setStyleSheet("color: #2c313a;")
        layout.addWidget(divider3)

        # Pipeline Status Checklist
        layout.addWidget(QLabel("Pipeline Status:"))
        self.pipeline_checklist = QVBoxLayout()
        self.pipeline_checklist.setSpacing(3)
        self.chk_labels = {
            "masks": QLabel("• Masks: -"),
            "tracks": QLabel("• 3D Tracks: -"),
            "barlow": QLabel("• Barlow: -"),
            "traces": QLabel("• Traces: -"),
        }
        for lbl in self.chk_labels.values():
            lbl.setStyleSheet("color: #7f848e; font-size: 11pt;")
            self.pipeline_checklist.addWidget(lbl)
        layout.addLayout(self.pipeline_checklist)

        layout.addStretch()

        # Quick Actions
        actions_box = QVBoxLayout()
        actions_box.setSpacing(6)

        btn_row1 = QHBoxLayout()
        self.btn_open_folder = QPushButton("Folder")
        self.btn_open_folder.setObjectName("actionButton")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self._action_open_folder)
        btn_row1.addWidget(self.btn_open_folder)

        self.btn_open_excel = QPushButton("Excel")
        self.btn_open_excel.setObjectName("actionButton")
        self.btn_open_excel.setEnabled(False)
        self.btn_open_excel.clicked.connect(self._action_open_excel)
        btn_row1.addWidget(self.btn_open_excel)

        self.btn_open_cfg = QPushButton("Config")
        self.btn_open_cfg.setObjectName("actionButton")
        self.btn_open_cfg.setEnabled(False)
        self.btn_open_cfg.clicked.connect(self._action_open_config)
        btn_row1.addWidget(self.btn_open_cfg)

        actions_box.addLayout(btn_row1)

        self.btn_copy_path = QPushButton("Copy Path")
        self.btn_copy_path.setObjectName("actionButton")
        self.btn_copy_path.setEnabled(False)
        self.btn_copy_path.clicked.connect(self._action_copy_path)
        actions_box.addWidget(self.btn_copy_path)

        layout.addLayout(actions_box)

        scroll.setWidget(panel)
        return scroll

    def _rebuild_strain_chips(self):
        """Rebuilds strain filter chips dynamically."""
        # Clear existing
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        strains = ["All"] + sorted(list(self.detected_strains))
        for strain in strains:
            chip = QPushButton(strain)
            chip.setObjectName("chipButton")
            chip.setCheckable(True)
            chip.setChecked(strain == self.active_strain_filter)
            chip.clicked.connect(lambda _, s=strain: self._on_strain_chip_clicked(s))
            self.chips_layout.addWidget(chip)

    def _on_strain_chip_clicked(self, strain: str):
        self.active_strain_filter = strain
        self._rebuild_strain_chips()
        self._apply_filters()

    # --------------------------------------------------------------------------
    # Keyboard Shortcuts
    # --------------------------------------------------------------------------

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key_Escape:
            if self.search_input.text():
                self.search_input.clear()
            else:
                self.reject()
        elif key == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if self.selected_project_path:
                self._on_launch_clicked()
        elif (modifiers & Qt.ControlModifier) and key == Qt.Key_F:
            self.search_input.setFocus()
            self.search_input.selectAll()
        elif key == Qt.Key_F5 or ((modifiers & Qt.ControlModifier) and key == Qt.Key_R):
            self._restart_scanner()
        else:
            super().keyPressEvent(event)

    # --------------------------------------------------------------------------
    # Scanner Worker Lifecycle
    # --------------------------------------------------------------------------

    def _start_scanner(self, bypass_cache: bool = False):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Scanning directories...")
        self.scanner_thread = RecordingScannerWorker(
            self.search_roots, self.recent_paths, bypass_cache=bypass_cache, parent=self
        )
        self.scanner_thread.recording_discovered.connect(self._on_recording_discovered)
        self.scanner_thread.recording_updated.connect(self._on_recording_updated)
        self.scanner_thread.scan_progress.connect(self._on_scan_progress)
        self.scanner_thread.scan_finished.connect(self._on_scan_finished)
        self.scanner_thread.start()

    def stop_scanner(self, wait: bool = True):
        """Stop the scanner. With ``wait=False`` (F5 refresh) the UI never blocks on a stuck
        network call: the old thread is detached from the UI and kept alive until it exits."""
        if hasattr(self, "scanner_thread") and self.scanner_thread is not None:
            thread = self.scanner_thread
            if thread.isRunning():
                thread.stop()
                try:
                    thread.recording_discovered.disconnect()
                    thread.recording_updated.disconnect()
                    thread.scan_progress.disconnect()
                    thread.scan_finished.disconnect()
                except Exception:
                    pass
                if wait:
                    thread.wait(2000)
                if thread.isRunning():
                    # Keep a reference so Qt doesn't destroy a running QThread
                    retired = self.__dict__.setdefault("_retired_scanners", [])
                    retired.append(thread)
                    thread.finished.connect(lambda t=thread: retired.remove(t) if t in retired else None)

    def _restart_scanner(self):
        self.stop_scanner(wait=False)

        prev_selection = self.selected_project_path

        # Clear UI table and state
        self.table.setRowCount(0)
        self.records_by_path.clear()
        self.row_by_path.clear()
        self.detected_strains.clear()
        self._rebuild_strain_chips()
        self.btn_launch.setEnabled(False)
        self._update_inspector(None)

        # Reload recent paths and search roots fresh
        self.recent_paths = [canonical_path(p) for p in load_history()]
        self.search_roots = [canonical_path(r) for r in DEFAULT_SEARCH_ROOTS]
        for cr in load_custom_roots():
            cr_norm = canonical_path(cr)
            if cr_norm and cr_norm not in self.search_roots:
                self.search_roots.append(cr_norm)
        for rp in self.recent_paths:
            try:
                p_dir = canonical_path(os.path.dirname(rp) if rp.lower().endswith(".yaml") else rp)
                parent_dir = canonical_path(os.path.dirname(p_dir))
                # Existence is checked by the scanner worker; no network stat on the UI thread.
                if parent_dir and not is_drive_root(parent_dir) and parent_dir not in self.search_roots:
                    self.search_roots.append(parent_dir)
            except Exception:
                pass

        if prev_selection:
            self.selected_project_path = canonical_path(prev_selection)

        self._start_scanner(bypass_cache=True)

    def _save_settings(self):
        if not self.isMinimized() and not self.isFullScreen():
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("is_maximized", self.isMaximized())
        self.settings.setValue("splitter_state", self.splitter.saveState())
        self.settings.setValue("load_tracklets", self.chk_full_tracklets.isChecked())
        if hasattr(self, "chk_keep_open") and self.standalone:
            self.settings.setValue("keep_open", self.chk_keep_open.isChecked())

    def closeEvent(self, event):
        self.stop_scanner()
        self._save_settings()
        super().closeEvent(event)

    def reject(self):
        self.stop_scanner()
        self._save_settings()
        super().reject()

    def accept(self):
        self.stop_scanner()
        self._save_settings()
        super().accept()

    # --------------------------------------------------------------------------
    # Scanner Worker Slots
    # --------------------------------------------------------------------------

    @Slot(dict)
    def _on_recording_discovered(self, record: dict):
        path = canonical_path(record.get("path"))
        record["path"] = path
        if "config_path" in record:
            record["config_path"] = canonical_path(record["config_path"])

        if path in self.records_by_path:
            return

        self.records_by_path[path] = record
        record["strain"] = clean_strain(record.get("strain", ""))
        strain = record.get("strain")
        if strain and strain not in self.detected_strains:
            self.detected_strains.add(strain)
            self._rebuild_strain_chips()

        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)

        row = self.table.rowCount()
        self.table.insertRow(row)

        self._populate_row(row, record)
        self._apply_row_filter(row)

        self.table.setSortingEnabled(sorting)
        self._schedule_update_counts()

        if self.selected_project_path and canonical_path(self.selected_project_path) in (
            path, canonical_path(record.get("config_path", ""))
        ):
            self.table.selectRow(row)
            self.btn_launch.setEnabled(True)
            self._update_inspector(record)
        elif self.table.rowCount() == 1 and not self.selected_project_path:
            self.table.selectRow(0)

    @Slot(dict)
    def _on_recording_updated(self, record: dict):
        path = canonical_path(record.get("path"))
        record["path"] = path
        if "config_path" in record:
            record["config_path"] = canonical_path(record["config_path"])

        self.records_by_path[path] = record
        record["strain"] = clean_strain(record.get("strain", ""))
        strain = record.get("strain")
        if strain and strain not in self.detected_strains:
            self.detected_strains.add(strain)
            self._rebuild_strain_chips()

        existing_item = self.row_by_path.get(path)
        target_row = existing_item.row() if existing_item is not None else -1

        if target_row >= 0:
            sorting = self.table.isSortingEnabled()
            self.table.setSortingEnabled(False)
            self._populate_row(target_row, record)
            self._apply_row_filter(target_row)
            self.table.setSortingEnabled(sorting)
        else:
            # Not in the table yet: let the discovery slot insert the row (it skips known paths)
            self.records_by_path.pop(path, None)
            self._on_recording_discovered(record)

        self._schedule_update_counts()

        # Update inspector if this is selected
        if self.selected_project_path and canonical_path(self.selected_project_path) in (
            path, canonical_path(record.get("config_path", ""))
        ):
            self._update_inspector(record)

    @Slot(str, int, int)
    def _on_scan_progress(self, msg: str, current: int, total: int):
        self.lbl_status.setText(msg)
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"%p% ({current}/{total})")

    @Slot()
    def _on_scan_finished(self):
        count = len(self.records_by_path)
        self.lbl_status.setText(f"Scan complete — {count} recordings loaded")
        self.progress_bar.setVisible(False)
        self._update_counts()
        if not self.selected_project_path and self.table.rowCount() > 0:
            for r in range(self.table.rowCount()):
                if not self.table.isRowHidden(r):
                    self.table.selectRow(r)
                    break

    # --------------------------------------------------------------------------
    # Table Population & Rendering
    # --------------------------------------------------------------------------

    def _populate_row(self, row: int, rec: dict):
        # Col 0: Recording Name
        name_item = SortableTableWidgetItem(rec.get("name", ""), sort_key=rec.get("name", "").lower())
        canon_path = canonical_path(rec.get("path", ""))
        name_item.setData(Qt.UserRole, canon_path)
        name_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
        if rec.get("is_recent"):
            name_color = "#e5c07b"
        elif recording_source(rec) == REFERENCE_SOURCE:
            name_color = "#61afef"  # reference recordings (annotated, to compare against)
        else:
            name_color = "#ffffff"
        name_item.setForeground(QColor(name_color))
        tip_parts = [rec.get("name", "")]
        if rec.get("is_recent"):
            tip_parts.append("(Recent Project)")
        tip_parts.append(f"Directory: {canon_path}")
        if rec.get("config_path"):
            tip_parts.append(f"Config: {canonical_path(rec['config_path'])}")
        name_item.setToolTip("\n".join(tip_parts))
        self.table.setItem(row, 0, name_item)
        self.row_by_path[canon_path] = name_item  # item.row() stays correct across sorting

        # Col 1: Date
        date_str = rec.get("date", "")
        date_item = SortableTableWidgetItem(date_str, sort_key=date_str)
        date_item.setTextAlignment(Qt.AlignCenter)
        date_item.setForeground(QColor("#abb2bf"))
        self.table.setItem(row, 1, date_item)

        # Col 2-5: Badges (Masks, Tracks, Traces, Barlow)
        badges = [
            ("has_masks", 2, "Masks"),
            ("has_tracks", 3, "3D Tracks"),
            ("has_traces", 4, "Calcium Traces"),
            ("has_barlow", 5, "Barlow Tracker"),
        ]
        for key, col, label in badges:
            val = rec.get(key, False)
            sym = "✓" if val else "✗"
            color = "#98c379" if val else "#5c6370"
            tip = f"{label}: Available" if val else f"{label}: Missing / Not generated"
            b_item = SortableTableWidgetItem(sym, sort_key=1 if val else 0)
            b_item.setTextAlignment(Qt.AlignCenter)
            b_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            b_item.setForeground(QColor(color))
            b_item.setToolTip(tip)
            self.table.setItem(row, col, b_item)

        # Col 6: Total Tracked Neurons
        tc = rec.get("tracked_count")
        tc_text = str(tc) if tc is not None else "-"
        tc_item = SortableTableWidgetItem(tc_text, sort_key=tc if tc is not None else -1)
        tc_item.setTextAlignment(Qt.AlignCenter)
        if tc is not None:
            tc_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            tc_item.setForeground(QColor("#61afef"))
        else:
            tc_item.setForeground(QColor("#5c6370"))
        self.table.setItem(row, 6, tc_item)

        # Col 7: ID'd Neurons Count
        ac = rec.get("annotated_count", 0)
        at = rec.get("annotated_total", 0)
        qm = rec.get("question_mark_count", 0)
        is_done = rec.get("is_fully_processed", False) and ac > 0 and qm == 0
        ann_names = rec.get("annotated_names", [])
        if at > 0 or ac > 0:
            if qm > 0:
                ann_text = f"⚠️ {ac} / {at}  ({qm}?)" if at > 0 else f"⚠️ {ac}  ({qm}?)"
                ann_color = "#e5c07b"
                ann_tip = (
                    f"⚠️ NEEDS MANUAL REVIEW:\n"
                    f"• {qm} unconfirmed (?) neuron IDs pending review\n"
                    f"• {ac - qm} confirmed IDs\n"
                    f"Double-click to open Quick Glance review dialog"
                )
            elif is_done:
                ann_text = f"✓ {ac} / {at}" if at > 0 else f"✓ {ac}"
                ann_color = "#98c379"
                ann_tip = (
                    f"✓ DONE: All {ac} neuron IDs confirmed (0 pending review)\n"
                    f"Double-click to open Quick Glance viewer"
                )
            else:
                ann_text = f"{ac} / {at}" if at > 0 else f"{ac}"
                ann_color = "#98c379" if ac > 0 else "#e06c75"
                if ann_names:
                    ann_tip = f"{ac} annotated neurons ({len(ann_names)} unique identities)\nDouble-click to open Quick Glance viewer"
                else:
                    ann_tip = f"{ac} of {at} neurons annotated\nDouble-click to open Quick Glance viewer"
            ann_sort = ac
        else:
            ann_text = "-"
            ann_sort = -1
            ann_color = "#5c6370"
            ann_tip = "No annotations available"
        ann_item = SortableTableWidgetItem(ann_text, sort_key=ann_sort)
        ann_item.setTextAlignment(Qt.AlignCenter)
        ann_item.setForeground(QColor(ann_color))
        if ac > 0:
            ann_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
        if qm > 0:
            ann_item.setBackground(QBrush(QColor("#352914")))
        elif is_done:
            ann_item.setBackground(QBrush(QColor("#182b1d")))
        ann_item.setToolTip(ann_tip)
        self.table.setItem(row, 7, ann_item)

    # --------------------------------------------------------------------------
    # Search & Filter Logic
    # --------------------------------------------------------------------------

    def _apply_row_filter(self, row: int):
        item0 = self.table.item(row, 0)
        if not item0:
            return
        path = canonical_path(item0.data(Qt.UserRole))
        rec = self.records_by_path.get(path, {})
        query = self.search_input.text().strip().lower()

        # Strain chip filter
        if self.active_strain_filter != "All":
            if rec.get("strain", "").upper() != self.active_strain_filter.upper():
                self.table.setRowHidden(row, True)
                return

        # Source filter (own / reference recordings)
        if hasattr(self, "source_combo") and self.source_combo.currentIndex() > 0:
            if recording_source(rec) != self.source_combo.currentText():
                self.table.setRowHidden(row, True)
                return

        # Neuron query, e.g. "n:AVAL, RIML": keep recordings that have any of them, ranked by how many
        wanted = parse_neuron_query(query)
        base_name = rec.get("name", "")
        if wanted is not None:
            n_match = count_neuron_matches(rec, wanted) if wanted else 0
            target = self._similarity_target
            if wanted and n_match > 0:
                label = f"{base_name}   ✓ {n_match}/{len(wanted)}"
                detail = describe_acquisition(rec)
                if detail:
                    label += f" · {detail}"
                if target and is_comparable(target, rec):
                    label += " · ≈ comparable"
                item0.setText(label)
                # Most requested neurons first; then same frame rate; then closest length
                item0.sort_key = (-n_match,) + (acquisition_similarity(target, rec) if target else (0, 0.0)) \
                    + (base_name.lower(),)
            else:
                item0.setText(base_name)
                item0.sort_key = (0, 1, float("inf"), base_name.lower())
                if wanted:
                    self.table.setRowHidden(row, True)
                    return
            query = ""  # fully handled; don't also substring-match the "n:..." text below
        elif item0.text() != base_name or not isinstance(getattr(item0, "sort_key", None), str):
            # Leaving neuron-query mode: restore the plain name and sort key (rows that did not match kept their
            # name but got a tuple key, which would otherwise mis-sort them in a name sort)
            item0.setText(base_name)
            item0.sort_key = base_name.lower()

        # Query filter
        if query:
            match_name = query in rec.get("name", "").lower()
            match_strain = query in rec.get("strain", "").lower()
            match_date = query in rec.get("date", "").lower()
            match_path = query in rec.get("path", "").lower()
            match_ann = any(query in name.lower() for name in rec.get("annotated_names", []))
            if not (match_name or match_strain or match_date or match_path or match_ann):
                self.table.setRowHidden(row, True)
                return

        # Preset: Done Only (Processed + Annotations exist + 0 pending '?')
        if hasattr(self, "chk_done_only") and self.chk_done_only.isChecked():
            is_done = rec.get("is_fully_processed", False) and rec.get("annotated_count", 0) > 0 and rec.get("question_mark_count", 0) == 0
            if not is_done:
                self.table.setRowHidden(row, True)
                return

        # Preset: Fully Processed
        if self.chk_processed_only.isChecked():
            if not rec.get("is_fully_processed", False):
                self.table.setRowHidden(row, True)
                return

        # Preset: Missing Annotations
        if self.chk_missing_annotations.isChecked():
            if not rec.get("missing_annotations", False):
                self.table.setRowHidden(row, True)
                return

        # Preset: Has '?' IDs (Needs Manual Review)
        if hasattr(self, "chk_question_marks") and self.chk_question_marks.isChecked():
            if rec.get("question_mark_count", 0) <= 0:
                self.table.setRowHidden(row, True)
                return

        # Preset: Recent Only
        if self.chk_recent_only.isChecked():
            if not rec.get("is_recent", False):
                self.table.setRowHidden(row, True)
                return

        self.table.setRowHidden(row, False)

    def _apply_filters(self):
        # Row text / sort keys change while filtering: keep the table from re-sorting under the loop
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        try:
            for r in range(self.table.rowCount()):
                self._apply_row_filter(r)
        finally:
            self.table.setSortingEnabled(sorting)
        if parse_neuron_query(self.search_input.text()):
            # Best matches (most of the requested neurons) first
            self.table.sortItems(0, Qt.AscendingOrder)
        else:
            self._similarity_target = None
        self._update_counts()

    def _schedule_update_counts(self):
        """Coalesce bursts of per-record updates (scanner emits one per project) into one refresh."""
        if getattr(self, "_counts_timer", None) is None:
            self._counts_timer = QTimer(self)
            self._counts_timer.setSingleShot(True)
            self._counts_timer.setInterval(150)
            self._counts_timer.timeout.connect(self._update_counts)
        if not self._counts_timer.isActive():
            self._counts_timer.start()

    def _update_counts(self):
        total = self.table.rowCount()
        visible = sum(1 for r in range(total) if not self.table.isRowHidden(r))
        all_recs = list(self.records_by_path.values())
        count_done = sum(1 for r in all_recs if r.get("is_fully_processed") and r.get("annotated_count", 0) > 0 and r.get("question_mark_count", 0) == 0)
        count_qm = sum(1 for r in all_recs if r.get("question_mark_count", 0) > 0)
        count_missing = sum(1 for r in all_recs if r.get("is_fully_processed") and r.get("annotated_count", 0) == 0)

        if hasattr(self, "chk_done_only"):
            self.chk_done_only.setText(f"✓ Done ({count_done})")
        if hasattr(self, "chk_question_marks"):
            self.chk_question_marks.setText(f"⚠️ Needs Review ({count_qm})")
        if hasattr(self, "chk_missing_annotations"):
            self.chk_missing_annotations.setText(f"Missing IDs ({count_missing})")

        self.badge_count_label.setText(
            f"Showing {visible} of {total} recordings  •  "
            f"<span style='color: #98c379; font-weight: bold;'>{count_done} Done</span>  •  "
            f"<span style='color: #e5c07b; font-weight: bold;'>{count_qm} Need Review (?)</span>"
        )

    # --------------------------------------------------------------------------
    # Inspector Sidebar Updates
    # --------------------------------------------------------------------------

    def _update_inspector(self, rec: Optional[dict]):
        if not rec:
            self.selected_record = None
            self.lbl_insp_name.setText("No recording selected")
            self.lbl_insp_strain.setVisible(False)
            self.lbl_insp_path.setText("")
            self.lbl_insp_acq.setText("Volumes: - | Date: -")
            self.lbl_insp_ann_stats.setText("0 / 0 (0.0%)")
            self.insp_progress.setValue(0)
            self.lbl_ann_identities_header.setText("Annotated Identities (0 unique)")
            self.lbl_bilateral_summary.setText("")
            self.btn_quick_glance.setText("🔍 View Annotated Neurons")
            self.btn_quick_glance.setEnabled(False)
            self.btn_find_reference.setEnabled(False)
            self.ann_filter_input.clear()
            self._clear_sidebar_badges()
            for k, lbl in self.chk_labels.items():
                lbl.setText(f"• {k.capitalize()}: -")
                lbl.setStyleSheet("color: #7f848e; font-size: 11pt;")
            self.btn_open_folder.setEnabled(False)
            self.btn_open_excel.setEnabled(False)
            self.btn_open_cfg.setEnabled(False)
            self.btn_copy_path.setEnabled(False)
            if hasattr(self, "frame_qm_alert"):
                self.frame_qm_alert.setVisible(False)
            return

        self.selected_record = rec
        self.lbl_insp_name.setText(rec.get("name", "Unknown"))
        strain = rec.get("strain", "")
        if strain:
            self.lbl_insp_strain.setText(strain)
            self.lbl_insp_strain.setVisible(True)
        else:
            self.lbl_insp_strain.setVisible(False)

        path_str = rec.get("path", "")
        self.lbl_insp_path.setText(path_str)

        # Volumes & acquisition
        vols = rec.get("num_volumes")
        vol_str = f"{vols:,} 3D volumes" if vols else "Volumes: N/A"
        date_str = rec.get("date", "N/A")
        self.lbl_insp_acq.setText(f"{vol_str}  |  {date_str}")

        # Annotation progress
        ac = rec.get("annotated_count", 0)
        at = rec.get("annotated_total", 0)
        pct = (ac / at * 100) if at > 0 else (0.0)
        self.lbl_insp_ann_stats.setText(f"{ac} / {at} ({pct:.1f}%)")
        self.insp_progress.setValue(int(pct))

        # Status / Review Alert
        qm_count = rec.get("question_mark_count", 0)
        is_done = rec.get("is_fully_processed", False) and ac > 0 and qm_count == 0
        if hasattr(self, "frame_qm_alert"):
            if qm_count > 0:
                self.frame_qm_alert.setStyleSheet("""
                    QFrame {
                        background-color: #2b2214;
                        border: 1px solid #7c5c28;
                        border-radius: 6px;
                        padding: 3px 6px;
                    }
                """)
                self.lbl_qm_alert.setText(f"⚠️ Needs Review ({qm_count} ? IDs)")
                self.lbl_qm_alert.setStyleSheet("color: #e5c07b; font-weight: bold; font-size: 10.5pt;")
                self.lbl_qm_alert.setToolTip(f"{qm_count} neurons from ID-transfer have uncertain '?' labels needing review")
                self.btn_qm_review.setText(f"Review '?' ({qm_count})")
                self.btn_qm_review.setVisible(True)
                self.frame_qm_alert.setVisible(True)
            elif is_done:
                self.frame_qm_alert.setStyleSheet("""
                    QFrame {
                        background-color: #172b1d;
                        border: 1px solid #2e7d32;
                        border-radius: 6px;
                        padding: 3px 6px;
                    }
                """)
                self.lbl_qm_alert.setText("✓ Complete & Confirmed")
                self.lbl_qm_alert.setStyleSheet("color: #98c379; font-weight: bold; font-size: 10.5pt;")
                self.lbl_qm_alert.setToolTip("All neuron IDs in this recording are confirmed (0 pending review)")
                self.btn_qm_review.setVisible(False)
                self.frame_qm_alert.setVisible(True)
            else:
                self.frame_qm_alert.setVisible(False)

        # Annotated Identities & Quick Glance Pane
        ann_names = rec.get("annotated_names", [])
        ann_details = rec.get("annotated_details", [])
        self.lbl_ann_identities_header.setText(f"Annotated Identities ({len(ann_names)} unique)")
        npairs, nunpaired = compute_bilateral_stats(ann_names)
        if ann_names:
            self.lbl_bilateral_summary.setText(f"{npairs} bilateral pairs, {nunpaired} unpaired")
        else:
            self.lbl_bilateral_summary.setText("No annotations yet")

        has_ann_or_excel = (len(ann_names) > 0 or len(ann_details) > 0 or bool(rec.get("excel_path")))
        self.btn_quick_glance.setEnabled(has_ann_or_excel)
        self.btn_find_reference.setEnabled(bool(self._question_mark_query_names(rec)))
        if len(ann_names) > 0:
            self.btn_quick_glance.setText(f"🔍 View Annotated Neurons ({len(ann_names)})")
        elif len(ann_details) > 0:
            self.btn_quick_glance.setText(f"🔍 View Annotated Neurons ({len(ann_details)})")
        else:
            self.btn_quick_glance.setText("🔍 View Annotated Neurons")

        # Rebuild badge chips
        self._rebuild_sidebar_badges(ann_names, ann_details)

        # Pipeline Checklist
        stages = [
            ("masks", "has_masks", "Masks"),
            ("tracks", "has_tracks", "3D Tracks"),
            ("barlow", "has_barlow", "Barlow"),
            ("traces", "has_traces", "Traces"),
        ]
        for key, prop, label in stages:
            done = rec.get(prop, False)
            sym = "✓" if done else "✗"
            col = "#98c379" if done else "#e06c75"
            self.chk_labels[key].setText(f"{sym} {label}")
            self.chk_labels[key].setStyleSheet(f"color: {col}; font-weight: {'bold' if done else 'normal'}; font-size: 11pt;")

        # Actions: the scan already found these paths; no file-system calls here, since every click on a row lands
        # here and each check on a slow Z: share can freeze the window (existence is checked on click instead)
        self.btn_open_folder.setEnabled(bool(path_str))
        self.btn_open_excel.setEnabled(bool(rec.get("excel_path")))
        self.btn_open_cfg.setEnabled(bool(rec.get("config_path")))
        self.btn_copy_path.setEnabled(bool(path_str))

    def _clear_sidebar_badges(self):
        self.ann_badges.clear()
        while self.ann_badges_layout.count() > 0:
            item = self.ann_badges_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _rebuild_sidebar_badges(self, ann_names: List[str], ann_details: List[dict]):
        self._clear_sidebar_badges()
        if not ann_names:
            placeholder = QLabel("No identities annotated yet")
            placeholder.setStyleSheet("color: #5c6370; font-size: 10pt; font-style: italic; padding: 2px;")
            self.ann_badges_layout.addWidget(placeholder)
            return

        name_to_tracks: Dict[str, List[str]] = {}
        for d in ann_details:
            t = d.get("track_id", "")
            id1 = d.get("id1", "")
            id2 = d.get("id2", "")
            if id1:
                name_to_tracks.setdefault(id1, []).append(t)
            if id2:
                name_to_tracks.setdefault(id2, []).append(t)

        for name in ann_names:
            is_qm = "?" in name
            tracks = name_to_tracks.get(name, [])
            if tracks:
                tip = f"{', '.join(tracks)} -> {name}\n(Click to inspect in Quick Glance)"
            else:
                tip = f"{name}\n(Click to inspect in Quick Glance)"

            chip = QPushButton(name)
            if is_qm:
                chip.setStyleSheet("""
                    QPushButton {
                        background-color: #3d311c;
                        color: #e5c07b;
                        border: 1px solid #9e7a3b;
                        border-radius: 4px;
                        padding: 2px 6px;
                        font-size: 11pt;
                        font-weight: bold;
                        min-height: 18px;
                    }
                    QPushButton:hover {
                        background-color: #524225;
                        border-color: #e5c07b;
                        color: #ffffff;
                    }
                """)
                tip = f"[UNCONFIRMED ID (?)]\n{tip}"
            else:
                chip.setObjectName("badgeChip")
            chip.setToolTip(tip)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda checked=False, n=name: self._open_quick_glance_dialog(filter_text=n))
            self.ann_badges_layout.addWidget(chip)
            self.ann_badges.append((name, chip))

    def _filter_sidebar_badges(self, text: str):
        query = text.strip().lower()
        for name, chip in self.ann_badges:
            chip.setVisible(query in name.lower() if query else True)

    @staticmethod
    def _question_mark_query_names(rec: Optional[dict]) -> List[str]:
        """The proposed names ('?' stripped) of a recording's uncertain neurons"""
        names = {str(n).replace("?", "").strip() for n in (rec or {}).get("question_mark_names", [])}
        return sorted(n for n in names if n)

    def _on_find_reference_clicked(self):
        names = self._question_mark_query_names(self.selected_record)
        if not names:
            return
        # Changing the combo already runs a filter pass (which clears the target while no neuron query is active),
        # so set the target last, right before the query that uses it
        self.source_combo.setCurrentText(REFERENCE_SOURCE)
        self._similarity_target = dict(self.selected_record)  # rank by similar frame rate / length as well
        self.search_input.setText("n:" + ", ".join(names))  # textChanged re-applies the filters

    def _on_quick_glance_clicked(self):
        if self.selected_record:
            self._open_quick_glance_dialog(self.selected_record)

    def _open_quick_glance_dialog(self, record: Optional[dict] = None, filter_text: str = ""):
        rec = record or self.selected_record
        if not rec:
            return
        dialog = QuickGlanceAnnotationDialog(rec, parent=self, filter_text=filter_text)
        dialog.exec_()

    # --------------------------------------------------------------------------
    # Context Menu & Quick Utilities
    # --------------------------------------------------------------------------

    def _show_context_menu(self, pos: QPoint):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        item0 = self.table.item(row, 0)
        if not item0:
            return
        path = item0.data(Qt.UserRole)
        rec = self.records_by_path.get(path, {})

        menu = QMenu(self)

        act_launch_fast = menu.addAction("Open Fast")
        act_launch_full = menu.addAction("Open Full")
        menu.addSeparator()

        act_view_annotations = menu.addAction("View Annotated Neurons...")
        act_view_annotations.setEnabled(
            len(rec.get("annotated_names", [])) > 0
            or len(rec.get("annotated_details", [])) > 0
            or bool(rec.get("excel_path"))
        )
        menu.addSeparator()

        act_folder = menu.addAction("Open in Explorer")
        act_excel = menu.addAction("Open in Excel")
        act_excel.setEnabled(bool(rec.get("excel_path")))

        act_cfg = menu.addAction("Open Config")
        act_cfg.setEnabled(bool(rec.get("config_path")))
        menu.addSeparator()

        act_copy_cfg = menu.addAction("Copy Config Path")
        act_copy_dir = menu.addAction("Copy Directory Path")

        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if not action:
            return

        cfg_path = rec.get("config_path", path)
        if action == act_launch_fast:
            self._launch_selected(cfg_path, load_tracklets=False)
        elif action == act_launch_full:
            self._launch_selected(cfg_path, load_tracklets=True)
        elif action == act_view_annotations:
            self._open_quick_glance_dialog(rec)
        elif action == act_folder:
            self._open_path(path)
        elif action == act_excel:
            self._open_path(rec.get("excel_path"))
        elif action == act_cfg:
            self._open_path(cfg_path)
        elif action == act_copy_cfg:
            QApplication.clipboard().setText(cfg_path)
            self.lbl_status.setText("Config path copied to clipboard")
        elif action == act_copy_dir:
            QApplication.clipboard().setText(path)
            self.lbl_status.setText("Directory path copied to clipboard")

    def _open_path(self, path: Optional[str]):
        """Open a file or folder with its default Windows app; say so if it is gone since the scan"""
        if path and os.path.exists(path):
            os.startfile(path)
        elif path:
            self.lbl_status.setText(f"Not found (moved or deleted since the last scan; F5 rescans): {path}")

    def _action_open_folder(self):
        if self.selected_record:
            self._open_path(self.selected_record["path"])

    def _action_open_excel(self):
        if self.selected_record:
            self._open_path(self.selected_record.get("excel_path"))

    def _action_open_config(self):
        if self.selected_record:
            self._open_path(self.selected_record.get("config_path"))

    def _action_copy_path(self):
        if self.selected_record:
            path = self.selected_record.get("config_path", self.selected_record["path"])
            QApplication.clipboard().setText(path)
            self.lbl_status.setText("Path copied to clipboard")

    # --------------------------------------------------------------------------
    # UI Interactions & Actions
    # --------------------------------------------------------------------------

    def _on_fast_mode_toggled(self, checked: bool):
        if checked:
            self.chk_full_tracklets.blockSignals(True)
            self.chk_full_tracklets.setChecked(False)
            self.chk_full_tracklets.blockSignals(False)
        elif not self.chk_full_tracklets.isChecked():
            self.chk_fast_mode.blockSignals(True)
            self.chk_fast_mode.setChecked(True)
            self.chk_fast_mode.blockSignals(False)

    def _on_full_tracklets_toggled(self, checked: bool):
        if checked:
            self.chk_fast_mode.blockSignals(True)
            self.chk_fast_mode.setChecked(False)
            self.chk_fast_mode.blockSignals(False)
        elif not self.chk_fast_mode.isChecked():
            self.chk_full_tracklets.blockSignals(True)
            self.chk_full_tracklets.setChecked(True)
            self.chk_full_tracklets.blockSignals(False)

    def _on_table_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_project_path = None
            self.btn_launch.setEnabled(False)
            self._update_inspector(None)
            return

        row = selected_rows[0].row()
        item0 = self.table.item(row, 0)
        if item0:
            path = canonical_path(item0.data(Qt.UserRole))
            rec = self.records_by_path.get(path, {})
            self.selected_project_path = canonical_path(rec.get("config_path", path))
            self.btn_launch.setEnabled(True)
            self._update_inspector(rec)

    def _on_table_double_clicked(self, item):
        self._on_table_selection_changed()
        if not item:
            return
        # If double clicked on "Annotated" (Col 7), open Quick Glance
        if item.column() == 7 and self.selected_record:
            self._open_quick_glance_dialog(self.selected_record)
        elif self.selected_project_path:
            self._launch_selected(self.selected_project_path, self.chk_full_tracklets.isChecked())

    def _on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Root Directory to Scan")
        if folder:
            canon_folder = canonical_path(folder)
            if canon_folder not in self.search_roots:
                self.search_roots.append(canon_folder)
                customs = load_custom_roots()
                if canon_folder not in [canonical_path(c) for c in customs]:
                    customs.append(canon_folder)
                    save_custom_roots(customs)
            self._restart_scanner()

    def _on_browse_file(self):
        initial_dir = os.path.dirname(self.recent_paths[0]) if self.recent_paths else None
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select project_config.yaml",
            initial_dir or "",
            "YAML files (*.yaml);;All files (*.*)"
        )
        if path:
            self._launch_selected(canonical_path(path), self.chk_full_tracklets.isChecked())

    def _on_launch_clicked(self):
        if not self.selected_project_path:
            QMessageBox.warning(self, "No Selection", "Please select a recording to open.")
            return

        self._launch_selected(self.selected_project_path, self.chk_full_tracklets.isChecked())

    def _launch_selected(self, project_path: str, load_tracklets: bool):
        """Dispatches project launch either via background subprocess or modal acceptance."""
        if not project_path:
            return

        project_path = canonical_path(resolve_existing_path(canonical_path(project_path)))

        # Resolve directory to config yaml if present
        if os.path.isdir(project_path):
            candidate = os.path.join(project_path, "project_config.yaml")
            if os.path.exists(candidate):
                project_path = canonical_path(candidate)

        self.selected_project_path = project_path
        self.load_tracklets = load_tracklets
        save_history(project_path)

        if self.standalone and self.chk_keep_open.isChecked():
            self._launch_trace_explorer_subprocess(project_path, load_tracklets)
        else:
            self.accept()

    def _launch_trace_explorer_subprocess(self, project_path: str, load_tracklets: bool):
        """Launches Trace Explorer as an independent background subprocess."""
        import subprocess
        python_exe = sys.executable
        launcher_script = os.path.abspath(__file__)
        cmd = [python_exe, "-X", "utf8", launcher_script, project_path]
        if load_tracklets:
            cmd.append("--load-tracklets")
        else:
            cmd.append("--fast")

        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(
                cmd,
                creationflags=creationflags,
                close_fds=False if sys.platform == "win32" else True
            )
            self.running_processes.append((proc, project_path))
            rec_name = os.path.basename(os.path.dirname(project_path)) if project_path.endswith(".yaml") else os.path.basename(project_path)
            mode_str = "Full" if load_tracklets else "Fast"
            self.lbl_status.setText(f"Running: {rec_name} [{mode_str}] (PID: {proc.pid})")
        except Exception as e:
            logging.error(f"Failed to launch subprocess: {e}")
            QMessageBox.critical(self, "Launch Error", f"Failed to launch Trace Explorer:\n{e}")


# ==============================================================================
# Prompt Entry Point (Backward-Compatible)
# ==============================================================================

def launch_gui_prompt(return_options: bool = False, standalone: bool = False) -> Any:
    """
    Shows the modernized WBFM Recording Dashboard & Launcher.

    Parameters:
        return_options (bool): If False (default), returns the selected project_path (str)
                               or None, maintaining full backward-compatibility with
                               legacy scripts like test_gui_ids.py.
                               If True, returns a tuple (project_path, load_tracklets).
        standalone (bool): If True, runs in persistent workstation mode where
                           recordings are launched as background subprocesses and the
                           dashboard remains open.
    """
    app = QApplication.instance()
    if app is None:
        # Prevent Qt from inflating fonts and widgets on Windows displays
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, False)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        app = QApplication(sys.argv)
    apply_app_icon(app)

    dialog = WBFMRecordingDashboard(standalone=standalone)
    result = dialog.exec_()
    dialog.stop_scanner()

    selected_path = dialog.selected_project_path if result == QDialog.Accepted else None
    load_tracklets = dialog.load_tracklets if result == QDialog.Accepted else False

    app.processEvents()

    if return_options:
        return selected_path, load_tracklets
    return selected_path


# ==============================================================================
# Main CLI Entry Point
# ==============================================================================

def main():
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    if QApplication.instance() is None:
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, False)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    parser = argparse.ArgumentParser(description="Launch WBFM Trace Explorer")
    parser.add_argument("project_path", nargs="?", default=None, help="Path to project_config.yaml")
    parser.add_argument("--fast", action="store_true", default=False, help="Fast mode: traces & IDs only, no tracklets")
    parser.add_argument("--load-tracklets", dest="load_tracklets", action="store_true", default=None, help="Load full 3D tracklets")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debug logging")
    args = parser.parse_args()

    project_path = args.project_path
    load_tracklets = False

    if args.load_tracklets:
        load_tracklets = True
    elif args.fast:
        load_tracklets = False

    if not project_path:
        # Launch modern Qt Dashboard in standalone workstation mode
        res = launch_gui_prompt(return_options=True, standalone=True)
        if not res or not res[0]:
            sys.exit(0)
        project_path, load_tracklets = res
    else:
        # Path passed directly via CLI
        if args.load_tracklets is None and not args.fast:
            load_tracklets = False

    if project_path:
        project_path = canonical_path(resolve_existing_path(canonical_path(project_path)))
        if os.path.isdir(project_path):
            candidate = os.path.join(project_path, "project_config.yaml")
            if os.path.exists(candidate):
                project_path = canonical_path(candidate)

    # Validate existence
    if project_path and os.path.exists(project_path):
        save_history(project_path)
    else:
        print(f"Error: Project path does not exist: {project_path}")
        sys.exit(1)

    print(f"Loading project: {project_path}")
    print(f"Mode: {'Full 3D Tracklets' if load_tracklets else 'Fast Mode (Traces & IDs Only)'}")
    print("Initializing Trace Explorer in Napari...")

    from wbfm.gui.utils.napari_trace_explorer import napari_trace_explorer_from_config

    try:
        napari_trace_explorer_from_config(
            project_path,
            load_tracklets=load_tracklets,
            force_tracklets_to_be_sparse=True,
            DEBUG=args.debug,
        )
    except AttributeError as e:
        if load_tracklets:
            print(f"Failed to load with tracklet interactivity ({e}); "
                  f"retrying without tracklets (traces/IDs are unaffected)...")
            napari_trace_explorer_from_config(
                project_path,
                load_tracklets=False,
                force_tracklets_to_be_sparse=True,
                DEBUG=args.debug,
            )
        else:
            raise


if __name__ == "__main__":
    main()
