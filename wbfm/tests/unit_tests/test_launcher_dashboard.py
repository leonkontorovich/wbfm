"""
Unit tests for the modernized WBFM Recording Dashboard & Launcher.
Tests history management, metadata extraction, background scanning over missing/disconnected paths,
sorting, and filtering logic.
"""
import os
import sys
import unittest
import tempfile
import json
import shutil
from unittest.mock import patch, MagicMock

# Ensure wbfm repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import launch_gui  # noqa: E402
from launch_gui import (
    canonical_path,
    get_project_fingerprint,
    load_history,
    load_history_entries,
    save_history,
    extract_metadata_for_project,
    RecordingScannerWorker,
    SortableTableWidgetItem,
    WBFMRecordingDashboard,
    QuickGlanceAnnotationDialog,
    compute_bilateral_stats,
    FlowLayout,
    DARK_THEME_QSS,
)

# The launcher is Windows-only (drive letters, os.startfile); these tests use Windows path semantics
windows_only = unittest.skipUnless(sys.platform == "win32", "Windows path semantics (launch_gui.py is Windows-only)")
from qtpy.QtWidgets import QApplication, QHeaderView, QScrollArea
from qtpy.QtCore import Qt, QTimer


class TestHistoryManagement(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_history_file = os.path.join(self.test_dir, ".recent_projects.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_empty_history(self):
        with patch("launch_gui.HISTORY_FILE", self.test_history_file):
            history = load_history()
            self.assertEqual(history, [])
            entries = load_history_entries()
            self.assertEqual(entries, [])

    def test_backward_compatibility_with_legacy_string_list(self):
        legacy_data = [
            "Z:/path/to/project1/project_config.yaml",
            "Z:/path/to/project2/project_config.yaml",
        ]
        with open(self.test_history_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        with patch("launch_gui.HISTORY_FILE", self.test_history_file):
            history = load_history()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0], legacy_data[0])

            entries = load_history_entries()
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["path"], legacy_data[0])

    def test_save_and_load_history_with_timestamps(self):
        with patch("launch_gui.HISTORY_FILE", self.test_history_file):
            p1 = "Z:/path/to/proj1/project_config.yaml"
            p2 = "Z:/path/to/proj2/project_config.yaml"
            save_history(p1)
            save_history(p2)

            history = load_history()
            self.assertEqual(len(history), 2)
            # Most recent must be first
            self.assertEqual(history[0], p2)
            self.assertEqual(history[1], p1)

            entries = load_history_entries()
            self.assertIn("timestamp", entries[0])
            self.assertIsNotNone(entries[0]["timestamp"])

            # Test deduplication
            save_history(p1)
            history_after = load_history()
            self.assertEqual(len(history_after), 2)
            self.assertEqual(history_after[0], p1)


class TestMetadataExtraction(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_extract_metadata_empty_dir(self):
        meta = extract_metadata_for_project(self.test_dir)
        self.assertEqual(meta["path"], self.test_dir)
        self.assertFalse(meta["has_masks"])
        self.assertFalse(meta["has_tracks"])
        self.assertFalse(meta["has_traces"])
        self.assertFalse(meta["has_barlow"])
        self.assertIsNone(meta["tracked_count"])
        self.assertEqual(meta["annotated_count"], 0)
        self.assertEqual(meta["annotated_names"], [])
        self.assertEqual(meta["annotated_details"], [])
        self.assertNotIn("landmarks", meta)
        self.assertFalse(meta["is_fully_processed"])

    def test_extract_metadata_mock_project(self):
        proj_dir = os.path.join(self.test_dir, "AX10059worm1-2026-04-10")
        os.makedirs(os.path.join(proj_dir, "1-segmentation"), exist_ok=True)
        os.makedirs(os.path.join(proj_dir, "3-tracking", "postprocessing"), exist_ok=True)
        os.makedirs(os.path.join(proj_dir, "3-tracking", "barlow_tracker"), exist_ok=True)
        os.makedirs(os.path.join(proj_dir, "4-traces"), exist_ok=True)

        # Create dummy indicator files
        with open(os.path.join(proj_dir, "1-segmentation", "metadata.pickle"), "wb") as f:
            f.write(b"dummy")
        with open(os.path.join(proj_dir, "3-tracking", "postprocessing", "combined_3d_tracks.h5"), "wb") as f:
            f.write(b"dummy")
        with open(os.path.join(proj_dir, "4-traces", "green_traces.h5"), "wb") as f:
            f.write(b"dummy")
        with open(os.path.join(proj_dir, "3-tracking", "barlow_tracker", "worm_tracker_barlow.pickle"), "wb") as f:
            f.write(b"dummy")

        meta = extract_metadata_for_project(proj_dir)
        self.assertEqual(meta["name"], "AX10059worm1-2026-04-10")
        self.assertEqual(meta["strain"], "AX10059")
        self.assertEqual(meta["date"], "2026-04-10")
        self.assertTrue(meta["has_masks"])
        self.assertTrue(meta["has_tracks"])
        self.assertTrue(meta["has_traces"])
        self.assertTrue(meta["has_barlow"])
        self.assertTrue(meta["is_fully_processed"])
        self.assertNotIn("landmarks", meta)

    def test_extract_metadata_with_annotations(self):
        import pandas as pd
        proj_dir = os.path.join(self.test_dir, "AX10059worm1-2026-04-10")
        ann_dir = os.path.join(proj_dir, "3-tracking", "manual_annotation")
        os.makedirs(ann_dir, exist_ok=True)

        df = pd.DataFrame({
            "Neuron ID": [1, 2, 3, 4],
            "ID1": ["AVAL", "AVAR", "AIBL", None],
            "ID2": [None, None, None, "AIBR"],
            "Certainty": [2, 2, 1, 1],
            "Notes": ["Anchor", "Anchor", "Tracked", "Uncertain"]
        })
        ann_path = os.path.join(ann_dir, "manual_annotation.xlsx")
        df.to_excel(ann_path, index=False)

        meta = extract_metadata_for_project(proj_dir)
        self.assertEqual(meta["annotated_total"], 4)
        self.assertEqual(meta["annotated_count"], 4)
        self.assertEqual(meta["annotated_names"], ["AIBL", "AIBR", "AVAL", "AVAR"])
        self.assertEqual(len(meta["annotated_details"]), 4)
        self.assertEqual(meta["annotated_details"][0]["track_id"], "neuron_001")
        self.assertEqual(meta["annotated_details"][0]["id1"], "AVAL")
        self.assertEqual(meta["annotated_details"][0]["confidence"], "2")
        self.assertEqual(meta["annotated_details"][0]["comment"], "Anchor")
        self.assertEqual(meta["annotated_details"][3]["id2"], "AIBR")

    def test_permission_error_excel_fallback(self):
        proj_dir = os.path.join(self.test_dir, "AX10059worm1-2026-04-10")
        ann_dir = os.path.join(proj_dir, "3-tracking", "manual_annotation")
        os.makedirs(ann_dir, exist_ok=True)
        ann_path = os.path.join(ann_dir, "manual_annotation.xlsx")
        with open(ann_path, "wb") as f:
            f.write(b"dummy")

        with patch("pandas.read_excel", side_effect=PermissionError("File locked by Excel")):
            meta = extract_metadata_for_project(proj_dir)
            self.assertEqual(meta["annotated_count"], 0)
            self.assertEqual(meta["annotated_names"], [])
            self.assertEqual(meta["annotated_details"], [])

    def test_candidate_annotation_paths(self):
        import pandas as pd
        proj_dir = os.path.join(self.test_dir, "AX10059worm2-2026-04-10")
        ann_dir = os.path.join(proj_dir, "3-tracking", "id_transfer_output", "hungarian")
        os.makedirs(ann_dir, exist_ok=True)
        df = pd.DataFrame({
            "Neuron ID": [1, 2],
            "ID1": ["AVAL", "AVAR"],
            "Certainty": [2, 2],
        })
        ann_path = os.path.join(ann_dir, "manual_annotation.xlsx")
        df.to_excel(ann_path, index=False)

        meta = extract_metadata_for_project(proj_dir)
        self.assertEqual(meta["annotated_count"], 2)
        self.assertEqual(meta["annotated_names"], ["AVAL", "AVAR"])
        self.assertEqual(meta["excel_path"], ann_path)

    def test_failed_reads_are_not_cached(self):
        import pandas as pd
        proj_dir = os.path.join(self.test_dir, "AX10059worm3-2026-04-10")
        ann_dir = os.path.join(proj_dir, "3-tracking", "manual_annotation")
        os.makedirs(ann_dir, exist_ok=True)
        ann_path = os.path.join(ann_dir, "manual_annotation.xlsx")
        pd.DataFrame({"Neuron ID": [1], "ID1": ["AVAL"]}).to_excel(ann_path, index=False)
        cache = {}
        with patch("pandas.read_excel", side_effect=ValueError("half-written file")):
            meta = extract_metadata_for_project(proj_dir, cache=cache)
        self.assertEqual(meta["annotated_count"], 0)
        self.assertTrue(cache[proj_dir]["read_errors"])
        # Within the retry interval the incomplete entry is reused (a broken file is not re-read on every scan) ...
        with patch("pandas.read_excel", side_effect=AssertionError("must not re-read yet")):
            extract_metadata_for_project(proj_dir, cache=cache)
        # ... afterwards it is read again, and a good result replaces it (instead of showing 0 IDs until F5)
        cache[proj_dir]["checked_at"] -= launch_gui.INCOMPLETE_CACHE_RETRY_S + 1
        meta = extract_metadata_for_project(proj_dir, cache=cache)
        self.assertEqual(meta["annotated_names"], ["AVAL"])
        self.assertNotIn("read_errors", cache[proj_dir])

    def test_open_in_excel_follows_the_newest_annotation_file(self):
        import pandas as pd
        proj_dir = os.path.join(self.test_dir, "AX10059worm4-2026-04-10")
        old = os.path.join(proj_dir, "3-tracking", "manual_annotation", "manual_annotation.xlsx")
        new = os.path.join(proj_dir, "3-tracking", "id_transfer_output", "hungarian", "manual_annotation.xlsx")
        for path, ids in ((old, ["AVAL"]), (new, ["AVAL", "RIML"])):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            pd.DataFrame({"Neuron ID": list(range(len(ids))), "ID1": ids}).to_excel(path, index=False)
        os.utime(old, (1_000_000_000, 1_000_000_000))
        meta = extract_metadata_for_project(proj_dir)
        self.assertEqual(meta["annotated_names"], ["AVAL", "RIML"])
        self.assertEqual(meta["excel_path"], new)


class TestScannerResilience(unittest.TestCase):
    """
    Deliverable 3: Standalone test ensuring background scanning handles missing
    network paths or disconnected drives gracefully without crashing.
    """
    def test_scanner_handles_missing_or_disconnected_paths(self):
        missing_roots = [
            r"X:\nonexistent_drive\LeonK\Analysis_Final_Worms",
            r"Z:\neurobiology\zimmer\LeonK\Analysis_Final_Worms_Strict_Chirality_No_Overlap",
            r"C:\fake_directory_that_does_not_exist_987654321",
        ]
        worker = RecordingScannerWorker(search_roots=missing_roots, recent_paths=[])

        discovered = []
        updated = []
        progress_messages = []
        is_finished = [False]

        worker.recording_discovered.connect(lambda d: discovered.append(d))
        worker.recording_updated.connect(lambda d: updated.append(d))
        worker.scan_progress.connect(lambda msg, c, t: progress_messages.append(msg))
        worker.scan_finished.connect(lambda: is_finished.__setitem__(0, True))

        # Run synchronously to verify run() completes without exceptions
        worker.run()

        self.assertTrue(is_finished[0], "Worker should emit scan_finished even if all paths are missing.")
        self.assertEqual(len(discovered), 0, "No projects should be discovered in missing paths.")
        self.assertGreater(len(progress_messages), 0, "Progress messages should be emitted.")


class TestSortableTableWidgetItem(unittest.TestCase):
    def test_numeric_sorting(self):
        item1 = SortableTableWidgetItem("25", sort_key=25)
        item2 = SortableTableWidgetItem("212", sort_key=212)
        # 25 < 212
        self.assertTrue(item1 < item2)
        self.assertFalse(item2 < item1)

    def test_none_numeric_sorting(self):
        item1 = SortableTableWidgetItem("-", sort_key=-1)
        item2 = SortableTableWidgetItem("5", sort_key=5)
        self.assertTrue(item1 < item2)

    def test_string_sorting(self):
        item_a = SortableTableWidgetItem("alpha", sort_key="alpha")
        item_b = SortableTableWidgetItem("beta", sort_key="beta")
        self.assertTrue(item_a < item_b)


class TestDashboardUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.dashboard = WBFMRecordingDashboard()

    def tearDown(self):
        if hasattr(self.dashboard, "scanner_thread") and self.dashboard.scanner_thread.isRunning():
            self.dashboard.scanner_thread.stop()
            self.dashboard.scanner_thread.wait(1000)
        self.dashboard.close()

    def test_dashboard_initialization(self):
        self.assertEqual(self.dashboard.table.columnCount(), 8)
        self.assertEqual(
            self.dashboard.columns,
            ["Recording", "Date", "Masks", "Tracks", "Traces", "Barlow", "Neurons", "Annotated"]
        )
        self.assertTrue(self.dashboard.chk_fast_mode.isChecked())
        self.assertFalse(self.dashboard.chk_full_tracklets.isChecked())

    def test_fast_mode_toggle_mutual_exclusivity(self):
        self.dashboard.chk_full_tracklets.setChecked(True)
        self.assertFalse(self.dashboard.chk_fast_mode.isChecked())
        self.assertTrue(self.dashboard.chk_full_tracklets.isChecked())

        self.dashboard.chk_fast_mode.setChecked(True)
        self.assertTrue(self.dashboard.chk_fast_mode.isChecked())
        self.assertFalse(self.dashboard.chk_full_tracklets.isChecked())

    def test_dashboard_filtering_logic(self):
        # Insert test records
        r1 = {
            "name": "AX10059worm1-2026-04-10",
            "path": r"C:\fake\AX10059worm1-2026-04-10",
            "config_path": r"C:\fake\AX10059worm1-2026-04-10\project_config.yaml",
            "date": "2026-04-10",
            "strain": "AX10059",
            "has_masks": True,
            "has_tracks": True,
            "has_traces": True,
            "has_barlow": True,
            "tracked_count": 212,
            "annotated_count": 25,
            "annotated_total": 212,
            "annotated_names": ["AVAL", "AVAR", "AIBL"],
            "annotated_details": [
                {"track_id": "neuron_001", "id1": "AVAL", "confidence": "2", "comment": ""},
                {"track_id": "neuron_002", "id1": "AVAR", "confidence": "2", "comment": ""},
                {"track_id": "neuron_003", "id1": "AIBL", "confidence": "1", "comment": ""},
            ],
            "is_fully_processed": True,
            "missing_annotations": False,
            "is_recent": True,
        }
        r2 = {
            "name": "ZIM2554worm2-2026-09-04",
            "path": r"C:\fake\ZIM2554worm2-2026-09-04",
            "config_path": r"C:\fake\ZIM2554worm2-2026-09-04\project_config.yaml",
            "date": "2026-09-04",
            "strain": "ZIM2554",
            "has_masks": True,
            "has_tracks": False,
            "has_traces": False,
            "has_barlow": False,
            "tracked_count": 180,
            "annotated_count": 0,
            "annotated_total": 0,
            "annotated_names": [],
            "annotated_details": [],
            "is_fully_processed": False,
            "missing_annotations": True,
            "is_recent": False,
        }
        self.dashboard._on_recording_discovered(r1)
        self.dashboard._on_recording_updated(r1)
        self.dashboard._on_recording_discovered(r2)
        self.dashboard._on_recording_updated(r2)

        # Test query filter by recording name
        self.dashboard.search_input.setText("ZIM2554")
        self.assertTrue(self.dashboard.table.isRowHidden(0))
        self.assertFalse(self.dashboard.table.isRowHidden(1))

        # Test query filter by annotated neuron identity
        self.dashboard.search_input.setText("AVAL")
        self.assertFalse(self.dashboard.table.isRowHidden(0))
        self.assertTrue(self.dashboard.table.isRowHidden(1))

        self.dashboard.search_input.setText("AIBL")
        self.assertFalse(self.dashboard.table.isRowHidden(0))
        self.assertTrue(self.dashboard.table.isRowHidden(1))

        # Clear search
        self.dashboard.search_input.setText("")
        self.assertFalse(self.dashboard.table.isRowHidden(0))
        self.assertFalse(self.dashboard.table.isRowHidden(1))

        # Filter fully processed
        self.dashboard.chk_processed_only.setChecked(True)
        self.assertFalse(self.dashboard.table.isRowHidden(0))
        self.assertTrue(self.dashboard.table.isRowHidden(1))
        self.dashboard.chk_processed_only.setChecked(False)

        # Filter missing annotations
        self.dashboard.chk_missing_annotations.setChecked(True)
        self.assertTrue(self.dashboard.table.isRowHidden(0))
        self.assertFalse(self.dashboard.table.isRowHidden(1))
        self.dashboard.chk_missing_annotations.setChecked(False)

        # Filter recent only
        self.dashboard.chk_recent_only.setChecked(True)
        self.assertFalse(self.dashboard.table.isRowHidden(0))
        self.assertTrue(self.dashboard.table.isRowHidden(1))

    def test_strain_chip_filtering(self):
        r1 = {
            "name": "AX10059worm1-2026-04-10",
            "path": r"C:\fake\AX10059worm1-2026-04-10",
            "config_path": r"C:\fake\AX10059worm1-2026-04-10\project_config.yaml",
            "date": "2026-04-10",
            "strain": "AX10059",
            "has_masks": True,
            "has_tracks": True,
            "has_traces": True,
            "has_barlow": True,
            "tracked_count": 212,
            "annotated_count": 25,
            "annotated_total": 212,
            "annotated_names": ["AVAL", "AVAR"],
            "annotated_details": [],
            "is_fully_processed": True,
            "missing_annotations": False,
            "is_recent": False,
        }
        r2 = {
            "name": "ZIM2554worm2-2026-09-04",
            "path": r"C:\fake\ZIM2554worm2-2026-09-04",
            "config_path": r"C:\fake\ZIM2554worm2-2026-09-04\project_config.yaml",
            "date": "2026-09-04",
            "strain": "ZIM2554",
            "has_masks": True,
            "has_tracks": False,
            "has_traces": False,
            "has_barlow": False,
            "tracked_count": 180,
            "annotated_count": 0,
            "annotated_total": 0,
            "annotated_names": [],
            "annotated_details": [],
            "is_fully_processed": False,
            "missing_annotations": True,
            "is_recent": False,
        }
        self.dashboard._on_recording_discovered(r1)
        self.dashboard._on_recording_updated(r1)
        self.dashboard._on_recording_discovered(r2)
        self.dashboard._on_recording_updated(r2)

        # Filter by AX10059 chip
        self.dashboard._on_strain_chip_clicked("AX10059")
        self.assertFalse(self.dashboard.table.isRowHidden(0))
        self.assertTrue(self.dashboard.table.isRowHidden(1))

        # Reset to All
        self.dashboard._on_strain_chip_clicked("All")
        self.assertFalse(self.dashboard.table.isRowHidden(0))
        self.assertFalse(self.dashboard.table.isRowHidden(1))

    def test_inspector_panel_update(self):
        rec = {
            "name": "AX10059worm1-2026-04-10",
            "path": r"C:\fake\AX10059worm1-2026-04-10",
            "config_path": r"C:\fake\AX10059worm1-2026-04-10\project_config.yaml",
            "date": "2026-04-10",
            "strain": "AX10059",
            "num_volumes": 2250,
            "has_masks": True,
            "has_tracks": True,
            "has_traces": True,
            "has_barlow": True,
            "tracked_count": 212,
            "annotated_count": 4,
            "annotated_total": 212,
            "annotated_names": ["AIBL", "AIBR", "AVAL", "AVAR"],
            "annotated_details": [
                {"track_id": "neuron_001", "id1": "AVAL", "confidence": "2", "comment": "Good"},
                {"track_id": "neuron_002", "id1": "AVAR", "confidence": "2", "comment": "Good"},
                {"track_id": "neuron_003", "id1": "AIBL", "confidence": "1", "comment": ""},
                {"track_id": "neuron_004", "id1": "AIBR", "confidence": "1", "comment": ""},
            ],
            "is_fully_processed": True,
            "missing_annotations": False,
            "is_recent": False,
        }
        self.dashboard._update_inspector(rec)
        self.assertEqual(self.dashboard.lbl_insp_name.text(), "AX10059worm1-2026-04-10")
        self.assertEqual(self.dashboard.lbl_insp_strain.text(), "AX10059")
        self.assertIn("2,250 3D volumes", self.dashboard.lbl_insp_acq.text())
        self.assertIn("4 / 212", self.dashboard.lbl_insp_ann_stats.text())
        self.assertIn("4 unique", self.dashboard.lbl_ann_identities_header.text())
        self.assertIn("2 bilateral pairs, 0 unpaired", self.dashboard.lbl_bilateral_summary.text())
        self.assertEqual(len(self.dashboard.ann_badges), 4)
        self.assertTrue(self.dashboard.btn_quick_glance.isEnabled())

    @windows_only
    def test_metadata_caching(self):
        from launch_gui import load_metadata_cache, save_metadata_cache
        test_cache = {
            r"C:\fake\proj": {
                "mtime": 12345.6,
                "metadata": {
                    "name": "cached_name",
                    "annotated_names": ["AVAL"],
                    "annotated_details": [{"track_id": "neuron_001", "id1": "AVAL"}],
                }
            },
            r"C:\fake\stale": {
                "mtime": 12345.6,
                "metadata": {"name": "stale_name"}
            }
        }
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            temp_cache_file = f.name

        try:
            with patch("launch_gui.CACHE_FILE", temp_cache_file):
                save_metadata_cache(test_cache)
                loaded = load_metadata_cache()
                self.assertIn(r"C:\fake\proj", loaded)
                self.assertEqual(loaded[r"C:\fake\proj"]["metadata"]["name"], "cached_name")
                # Stale entry without annotated_names must be excluded
                self.assertNotIn(r"C:\fake\stale", loaded)
        finally:
            if os.path.exists(temp_cache_file):
                os.remove(temp_cache_file)

    def test_launch_gui_prompt_dismissal(self):
        from launch_gui import launch_gui_prompt
        # Automatically reject dialog after 50ms using QTimer
        def auto_reject():
            for w in QApplication.topLevelWidgets():
                if isinstance(w, WBFMRecordingDashboard):
                    w.reject()
        QTimer.singleShot(50, auto_reject)
        res = launch_gui_prompt(return_options=False)
        self.assertIsNone(res)

        QTimer.singleShot(50, auto_reject)
        path, fast = launch_gui_prompt(return_options=True)
        self.assertIsNone(path)

    def test_window_sizing_and_flags(self):
        """Verify window flags support minimization, maximization, and sizing grip."""
        flags = self.dashboard.windowFlags()
        self.assertTrue(bool(flags & Qt.Window))
        self.assertTrue(bool(flags & Qt.WindowMinMaxButtonsHint))
        self.assertTrue(bool(flags & Qt.WindowCloseButtonHint))
        self.assertTrue(self.dashboard.isSizeGripEnabled())
        self.assertEqual(self.dashboard.minimumWidth(), 720)
        self.assertEqual(self.dashboard.minimumHeight(), 420)

    @windows_only
    def test_launch_selected_keep_open_standalone(self):
        """Verify dashboard stays open and launches subprocess in standalone mode with keep_open=True."""
        standalone_dialog = WBFMRecordingDashboard(standalone=True)
        try:
            standalone_dialog.chk_keep_open.setChecked(True)
            with unittest.mock.patch.object(standalone_dialog, "_launch_trace_explorer_subprocess") as mock_sub, \
                 unittest.mock.patch.object(standalone_dialog, "accept") as mock_accept:
                standalone_dialog._launch_selected(r"C:\fake\project_config.yaml", load_tracklets=False)
                mock_sub.assert_called_once_with(r"C:\fake\project_config.yaml", False)
                mock_accept.assert_not_called()
        finally:
            standalone_dialog.stop_scanner()
            standalone_dialog.close()

    def test_launch_selected_close_when_keep_open_false(self):
        """Verify dashboard calls accept() when keep_open is unchecked in standalone mode."""
        standalone_dialog = WBFMRecordingDashboard(standalone=True)
        try:
            standalone_dialog.chk_keep_open.setChecked(False)
            with unittest.mock.patch.object(standalone_dialog, "_launch_trace_explorer_subprocess") as mock_sub, \
                 unittest.mock.patch.object(standalone_dialog, "accept") as mock_accept:
                standalone_dialog._launch_selected(r"C:\fake\project_config.yaml", load_tracklets=True)
                mock_sub.assert_not_called()
                mock_accept.assert_called_once()
        finally:
            standalone_dialog.stop_scanner()
            standalone_dialog.close()

    def test_launch_selected_in_modal_mode(self):
        """Verify modal picker mode (standalone=False) always calls accept()."""
        modal_dialog = WBFMRecordingDashboard(standalone=False)
        try:
            self.assertFalse(modal_dialog.chk_keep_open.isVisible())
            with unittest.mock.patch.object(modal_dialog, "_launch_trace_explorer_subprocess") as mock_sub, \
                 unittest.mock.patch.object(modal_dialog, "accept") as mock_accept:
                modal_dialog._launch_selected(r"C:\fake\project_config.yaml", load_tracklets=False)
                mock_sub.assert_not_called()
                mock_accept.assert_called_once()
        finally:
            modal_dialog.stop_scanner()
            modal_dialog.close()

    def test_clean_ui_no_emojis(self):
        """Verify buttons and labels avoid superfluous emojis."""
        self.assertEqual(self.dashboard.btn_copy_path.text(), "Copy Path")
        self.assertNotIn("📋", self.dashboard.btn_copy_path.text())
        self.assertNotIn("🚀", self.dashboard.btn_launch.text())


    def test_sidebar_badge_live_filter(self):
        """Verify live filtering of sidebar badges."""
        rec = {
            "name": "TestRecording",
            "annotated_names": ["AVAL", "AVAR", "SMDVL", "SMDVR"],
            "annotated_details": [
                {"track_id": "neuron_001", "id1": "AVAL"},
                {"track_id": "neuron_002", "id1": "AVAR"},
                {"track_id": "neuron_003", "id1": "SMDVL"},
                {"track_id": "neuron_004", "id1": "SMDVR"},
            ]
        }
        self.dashboard._update_inspector(rec)
        self.assertEqual(len(self.dashboard.ann_badges), 4)

        # Filter for SMD
        self.dashboard.ann_filter_input.setText("SMD")
        for name, chip in self.dashboard.ann_badges:
            if "SMD" in name:
                self.assertFalse(chip.isHidden())
            else:
                self.assertTrue(chip.isHidden())

        # Clear filter
        self.dashboard.ann_filter_input.setText("")
        for name, chip in self.dashboard.ann_badges:
            self.assertFalse(chip.isHidden())

    def test_table_double_click_behavior(self):
        """Verify double clicking annotated columns opens Quick Glance while other columns launch."""
        rec = {
            "name": "AX10059worm1-2026-04-10",
            "path": r"C:\fake\AX10059worm1-2026-04-10",
            "config_path": r"C:\fake\AX10059worm1-2026-04-10\project_config.yaml",
            "annotated_names": ["AVAL"],
            "annotated_details": [{"track_id": "neuron_001", "id1": "AVAL"}]
        }
        self.dashboard._on_recording_discovered(rec)
        self.dashboard._on_recording_updated(rec)
        self.dashboard.table.selectRow(0)

        with unittest.mock.patch.object(self.dashboard, "_open_quick_glance_dialog") as mock_glance, \
             unittest.mock.patch.object(self.dashboard, "_launch_selected") as mock_launch:
            # Double click on Column 7 (Annotated)
            item_ann = self.dashboard.table.item(0, 7)
            self.dashboard._on_table_double_clicked(item_ann)
            mock_glance.assert_called_once()
            mock_launch.assert_not_called()

        with unittest.mock.patch.object(self.dashboard, "_open_quick_glance_dialog") as mock_glance, \
             unittest.mock.patch.object(self.dashboard, "_launch_selected") as mock_launch:
            # Double click on Column 0 (Recording) -> should launch
            item_rec = self.dashboard.table.item(0, 0)
            self.dashboard._on_table_double_clicked(item_rec)
            mock_glance.assert_not_called()
            mock_launch.assert_called_once()

        with unittest.mock.patch.object(self.dashboard, "_open_quick_glance_dialog") as mock_glance, \
             unittest.mock.patch.object(self.dashboard, "_launch_selected") as mock_launch:
            # Double click on Column 1 (Date) -> should launch
            item_date = self.dashboard.table.item(0, 1)
            self.dashboard._on_table_double_clicked(item_date)
            mock_glance.assert_not_called()
            mock_launch.assert_called_once()

    def test_columns_streamlined(self):
        """Verify dashboard table has exactly 8 columns and excludes Identities Preview and Location."""
        self.assertEqual(len(self.dashboard.columns), 8)
        self.assertNotIn("Identities Preview", self.dashboard.columns)
        self.assertNotIn("Location", self.dashboard.columns)
        self.assertEqual(
            self.dashboard.columns,
            ["Recording", "Date", "Masks", "Tracks", "Traces", "Barlow", "Neurons", "Annotated"]
        )
        header = self.dashboard.table.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(0), QHeaderView.Stretch)

    def test_inspector_scroll_and_sizing(self):
        """Verify inspector panel is wrapped in QScrollArea and respects minimum width to prevent squishing."""
        self.assertIsInstance(self.dashboard.inspector_panel, QScrollArea)
        self.assertGreaterEqual(self.dashboard.inspector_panel.minimumWidth(), 280)

    def test_quick_glance_button_dynamic_text(self):
        """Verify Quick Glance button text reflects annotated count dynamically."""
        rec_empty = {"name": "EmptyRec", "annotated_names": [], "annotated_details": []}
        self.dashboard._update_inspector(rec_empty)
        self.assertEqual(self.dashboard.btn_quick_glance.text(), "🔍 View Annotated Neurons")
        self.assertFalse(self.dashboard.btn_quick_glance.isEnabled())

        rec_with_ann = {
            "name": "PopulatedRec",
            "annotated_names": ["AVAL", "AVAR"],
            "annotated_details": [{"track_id": "neuron_001", "id1": "AVAL"}, {"track_id": "neuron_002", "id1": "AVAR"}],
        }
        self.dashboard._update_inspector(rec_with_ann)
        self.assertEqual(self.dashboard.btn_quick_glance.text(), "🔍 View Annotated Neurons (2)")
        self.assertTrue(self.dashboard.btn_quick_glance.isEnabled())


class TestQuickGlanceAnnotationDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_dialog_instantiation_and_table_population(self):
        record = {
            "name": "AX10059worm1-2026-04-10",
            "tracked_count": 180,
            "annotated_count": 4,
            "annotated_names": ["AIBL", "AIBR", "AVAL", "AVAR"],
            "annotated_details": [
                {"track_id": "neuron_001", "id1": "AVAL", "id2": "", "confidence": "2", "comment": "Primary anchor"},
                {"track_id": "neuron_002", "id1": "AVAR", "id2": "", "confidence": "2", "comment": "Primary anchor"},
                {"track_id": "neuron_003", "id1": "AIBL", "id2": "", "confidence": "1", "comment": "Tracked"},
                {"track_id": "neuron_004", "id1": "", "id2": "AIBR", "confidence": "0", "comment": "Tentative"},
            ]
        }
        dialog = QuickGlanceAnnotationDialog(record=record)
        try:
            self.assertEqual(dialog.table.columnCount(), 5)
            self.assertEqual(dialog.table.rowCount(), 4)
            self.assertEqual(dialog.columns, ["Neuron #", "Primary ID", "Alternative ID", "Confidence / Status", "Notes"])

            # Check row 0 data
            self.assertEqual(dialog.table.item(0, 0).text(), "neuron_001")
            self.assertEqual(dialog.table.item(0, 1).text(), "AVAL")
            self.assertEqual(dialog.table.item(0, 2).text(), "")
            self.assertEqual(dialog.table.item(0, 3).text(), "2")
            self.assertEqual(dialog.table.item(0, 4).text(), "Primary anchor")

            # Check row 3 alternative ID
            self.assertEqual(dialog.table.item(3, 1).text(), "")
            self.assertEqual(dialog.table.item(3, 2).text(), "AIBR")

            # Check summary header
            summary_text = dialog.lbl_summary.text()
            self.assertIn("Total Annotated: 4 / 180", summary_text)
            self.assertIn("Unique Classes: 2", summary_text)

            # Test live filtering
            dialog.search_input.setText("AVA")
            self.assertFalse(dialog.table.isRowHidden(0))
            self.assertFalse(dialog.table.isRowHidden(1))
            self.assertTrue(dialog.table.isRowHidden(2))
            self.assertTrue(dialog.table.isRowHidden(3))
            self.assertEqual(dialog.lbl_filter_count.text(), "Showing 2 of 4")

            # Clear filter
            dialog.search_input.setText("")
            self.assertEqual(dialog.lbl_filter_count.text(), "Showing 4 of 4")

            # Test Copy ID List
            dialog._copy_id_list()
            clipboard_text = QApplication.clipboard().text()
            self.assertEqual(clipboard_text, "AIBL, AIBR, AVAL, AVAR")
        finally:
            dialog.close()


class TestBilateralAndFlowLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def test_compute_bilateral_stats(self):
        # Empty
        p, u = compute_bilateral_stats([])
        self.assertEqual(p, 0)
        self.assertEqual(u, 0)

        # Single complete pair
        p, u = compute_bilateral_stats(["AVAL", "AVAR"])
        self.assertEqual(p, 1)
        self.assertEqual(u, 0)

        # Multiple pairs + unpaired
        p, u = compute_bilateral_stats(["AVAL", "AVAR", "AIBL", "AIBR", "DVA"])
        self.assertEqual(p, 2)
        self.assertEqual(u, 1)

        # No bilateral suffixes
        p, u = compute_bilateral_stats(["AQR", "URX", "IL2"])
        self.assertEqual(p, 0)
        self.assertEqual(u, 3)

        # Unpaired with L but missing R
        p, u = compute_bilateral_stats(["AVAL", "DVA"])
        self.assertEqual(p, 0)
        self.assertEqual(u, 2)

    def test_flow_layout_basics(self):
        from qtpy.QtWidgets import QWidget, QPushButton
        container = QWidget()
        layout = FlowLayout(container, margin=2, spacing=4)
        btn1 = QPushButton("Btn1")
        btn2 = QPushButton("Btn2")
        layout.addWidget(btn1)
        layout.addWidget(btn2)

        self.assertEqual(layout.count(), 2)
        self.assertEqual(layout.itemAt(0).widget(), btn1)
        self.assertTrue(layout.hasHeightForWidth())
        self.assertGreater(layout.heightForWidth(200), 0)



class TestCanonicalPathAndFingerprinting(unittest.TestCase):
    @windows_only
    def test_canonical_path_windows_slashes(self):
        p_fwd = "Z:/neurobiology/zimmer/LeonK/Lit_immob/ZIM2165_Litworm4-2026-09-17"
        p_back = r"Z:\neurobiology\zimmer\LeonK\Lit_immob\ZIM2165_Litworm4-2026-09-17"
        p_lower = r"z:\neurobiology\zimmer\LeonK\Lit_immob\ZIM2165_Litworm4-2026-09-17"
        p_trailing = "Z:/neurobiology/zimmer/LeonK/Lit_immob/ZIM2165_Litworm4-2026-09-17/"

        c_fwd = canonical_path(p_fwd)
        c_back = canonical_path(p_back)
        c_lower = canonical_path(p_lower)
        c_trailing = canonical_path(p_trailing)

        self.assertEqual(c_fwd, c_back)
        self.assertEqual(c_fwd, c_lower)
        self.assertEqual(c_fwd, c_trailing)
        self.assertTrue(c_fwd.startswith("Z:\\"))

    def test_get_project_fingerprint_invalidation(self):
        with tempfile.TemporaryDirectory() as td:
            proj_dir = os.path.join(td, "test_proj")
            os.makedirs(proj_dir)
            with open(os.path.join(proj_dir, "project_config.yaml"), "w") as f:
                f.write("test: true\n")

            fp1 = get_project_fingerprint(proj_dir)
            fp1_repeat = get_project_fingerprint(proj_dir)
            self.assertEqual(fp1, fp1_repeat, "Fingerprint should be deterministic for untouched project")

            # Add tracking file
            post_dir = os.path.join(proj_dir, "3-tracking", "postprocessing")
            os.makedirs(post_dir)
            tracks_file = os.path.join(post_dir, "combined_3d_tracks.h5")
            with open(tracks_file, "wb") as f:
                f.write(b"dummy_tracks")

            fp2 = get_project_fingerprint(proj_dir)
            self.assertNotEqual(fp1, fp2, "Creating combined_3d_tracks.h5 should invalidate fingerprint")

            # Add manual annotation excel
            ann_dir = os.path.join(proj_dir, "3-tracking", "manual_annotation")
            os.makedirs(ann_dir)
            ann_file = os.path.join(ann_dir, "manual_annotation.xlsx")
            with open(ann_file, "wb") as f:
                f.write(b"dummy_excel_1")

            fp3 = get_project_fingerprint(proj_dir)
            self.assertNotEqual(fp2, fp3, "Creating manual_annotation.xlsx should invalidate fingerprint")


class TestDeduplicationAndStateUpdates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.dashboard = WBFMRecordingDashboard()

    def tearDown(self):
        self.dashboard.stop_scanner()
        self.dashboard.close()

    @windows_only
    def test_discovery_deduplication_different_slashes(self):
        r1 = {
            "name": "ZIM2165_Litworm4-2026-09-17",
            "path": "Z:/neurobiology/zimmer/LeonK/Lit_immob/ZIM2165_Litworm4-2026-09-17",
            "config_path": "Z:/neurobiology/zimmer/LeonK/Lit_immob/ZIM2165_Litworm4-2026-09-17/project_config.yaml",
            "date": "2026-09-17",
            "strain": "ZIM2165",
            "has_masks": True,
            "has_tracks": False,
            "has_traces": False,
            "has_barlow": False,
            "tracked_count": None,
            "annotated_count": 0,
            "annotated_total": 0,
            "annotated_names": [],
            "annotated_details": [],
            "is_fully_processed": False,
            "missing_annotations": False,
            "is_recent": True,
        }
        r2 = {
            "name": "ZIM2165_Litworm4-2026-09-17",
            "path": r"Z:\neurobiology\zimmer\LeonK\Lit_immob\ZIM2165_Litworm4-2026-09-17",
            "config_path": r"Z:\neurobiology\zimmer\LeonK\Lit_immob\ZIM2165_Litworm4-2026-09-17\project_config.yaml",
            "date": "2026-09-17",
            "strain": "ZIM2165",
            "has_masks": True,
            "has_tracks": False,
            "has_traces": False,
            "has_barlow": False,
            "tracked_count": None,
            "annotated_count": 0,
            "annotated_total": 0,
            "annotated_names": [],
            "annotated_details": [],
            "is_fully_processed": False,
            "missing_annotations": False,
            "is_recent": False,
        }

        self.dashboard._on_recording_discovered(r1)
        self.assertEqual(self.dashboard.table.rowCount(), 1)

        # Emitting duplicate with backslashes should not insert duplicate row
        self.dashboard._on_recording_discovered(r2)
        self.assertEqual(self.dashboard.table.rowCount(), 1, "Duplicate recording path with different slashes must not create duplicate table row")
        self.assertEqual(len(self.dashboard.records_by_path), 1)

    @windows_only
    def test_update_matches_differently_slashed_path(self):
        r1 = {
            "name": "ZIM2165_Litworm4-2026-09-17",
            "path": "Z:/neurobiology/zimmer/LeonK/Lit_immob/ZIM2165_Litworm4-2026-09-17",
            "config_path": "Z:/neurobiology/zimmer/LeonK/Lit_immob/ZIM2165_Litworm4-2026-09-17/project_config.yaml",
            "date": "2026-09-17",
            "strain": "ZIM2165",
            "has_masks": False,
            "has_tracks": False,
            "has_traces": False,
            "has_barlow": False,
            "tracked_count": None,
            "annotated_count": 0,
            "annotated_total": 0,
            "annotated_names": [],
            "annotated_details": [],
            "is_fully_processed": False,
            "missing_annotations": False,
            "is_recent": True,
        }
        self.dashboard._on_recording_discovered(r1)
        self.assertEqual(self.dashboard.table.rowCount(), 1)
        self.assertEqual(self.dashboard.table.item(0, 6).text(), "-")

        # Update with backslashes and newly completed tracks
        r1_updated = dict(r1)
        r1_updated["path"] = r"Z:\neurobiology\zimmer\LeonK\Lit_immob\ZIM2165_Litworm4-2026-09-17"
        r1_updated["has_tracks"] = True
        r1_updated["tracked_count"] = 185

        self.dashboard._on_recording_updated(r1_updated)
        self.assertEqual(self.dashboard.table.rowCount(), 1, "Updating record should not create duplicate row")
        self.assertEqual(self.dashboard.table.item(0, 6).text(), "185", "Tracked count must update properly")
        self.assertEqual(self.dashboard.table.item(0, 3).text(), "✓", "3D Tracks badge must update to checkmark")

    def test_discovery_applies_row_filter_immediately(self):
        # Set an active filter
        self.dashboard.search_input.setText("ZIM2554")

        # Discover a non-matching recording
        r_other = {
            "name": "AX10059worm1-2026-04-10",
            "path": r"C:\fake\AX10059worm1-2026-04-10",
            "config_path": r"C:\fake\AX10059worm1-2026-04-10\project_config.yaml",
            "date": "2026-04-10",
            "strain": "AX10059",
            "is_recent": False,
        }
        self.dashboard._on_recording_discovered(r_other)
        row = self.dashboard.table.rowCount() - 1
        self.assertTrue(self.dashboard.table.isRowHidden(row), "Newly discovered non-matching row must be filtered immediately")

    def test_cache_invalidation_when_indicator_file_added(self):
        with tempfile.TemporaryDirectory() as td:
            proj_dir = os.path.join(td, "worm_proj")
            os.makedirs(proj_dir)
            cfg_file = os.path.join(proj_dir, "project_config.yaml")
            with open(cfg_file, "w") as f:
                f.write("dummy: 1\n")

            cache = {}
            meta1 = extract_metadata_for_project(proj_dir, cache=cache)
            self.assertFalse(meta1["has_tracks"])
            self.assertIn(canonical_path(proj_dir), cache)

            # Subsequent call returns cached
            meta1_cached = extract_metadata_for_project(proj_dir, cache=cache)
            self.assertFalse(meta1_cached["has_tracks"])

            # Add tracking file into subdirectory
            post_dir = os.path.join(proj_dir, "3-tracking", "postprocessing")
            os.makedirs(post_dir)
            with open(os.path.join(post_dir, "combined_3d_tracks.h5"), "wb") as f:
                f.write(b"dummy_tracks")

            # Even with same cache, new file must invalidate fingerprint and update metadata
            meta2 = extract_metadata_for_project(proj_dir, cache=cache)
            self.assertTrue(meta2["has_tracks"], "Cache must be invalidated when combined_3d_tracks.h5 is added")

    def test_done_and_needs_review_filters_and_status_banner(self):
        """Verify Done vs Needs Review preset filters and inspector status card rendering."""
        r_done = {
            "name": "worm_done",
            "path": r"C:\fake\worm_done",
            "config_path": r"C:\fake\worm_done\project_config.yaml",
            "date": "2026-09-18",
            "strain": "ZIM2165",
            "has_masks": True,
            "has_tracks": True,
            "has_traces": True,
            "has_barlow": True,
            "is_fully_processed": True,
            "tracked_count": 200,
            "annotated_count": 190,
            "annotated_total": 200,
            "question_mark_count": 0,
            "has_question_marks": False,
            "annotated_names": ["AVAL", "AVAR"],
            "is_recent": False,
        }
        r_review = {
            "name": "worm_review",
            "path": r"C:\fake\worm_review",
            "config_path": r"C:\fake\worm_review\project_config.yaml",
            "date": "2026-09-18",
            "strain": "ZIM2165",
            "has_masks": True,
            "has_tracks": True,
            "has_traces": True,
            "has_barlow": True,
            "is_fully_processed": True,
            "tracked_count": 200,
            "annotated_count": 185,
            "annotated_total": 200,
            "question_mark_count": 14,
            "has_question_marks": True,
            "annotated_names": ["AVAL", "AVAR", "CEPDR?"],
            "question_mark_names": ["CEPDR?"],
            "is_recent": False,
        }
        self.dashboard.table.setRowCount(0)
        self.dashboard.records_by_path.clear()
        self.dashboard._on_recording_discovered(r_done)
        self.dashboard._on_recording_discovered(r_review)

        self.assertEqual(self.dashboard.table.rowCount(), 2)

        # Check Done filter
        self.dashboard.chk_done_only.setChecked(True)
        self.assertFalse(self.dashboard.table.isRowHidden(0), "Done worm should be visible")
        self.assertTrue(self.dashboard.table.isRowHidden(1), "Needs review worm should be hidden")
        self.dashboard.chk_done_only.setChecked(False)

        # Check Needs Review filter
        self.dashboard.chk_question_marks.setChecked(True)
        self.assertTrue(self.dashboard.table.isRowHidden(0), "Done worm should be hidden")
        self.assertFalse(self.dashboard.table.isRowHidden(1), "Needs review worm should be visible")
        self.dashboard.chk_question_marks.setChecked(False)

        # Check Inspector Status banner for Done
        self.dashboard._update_inspector(r_done)
        self.assertFalse(self.dashboard.frame_qm_alert.isHidden())
        self.assertIn("Complete & Confirmed", self.dashboard.lbl_qm_alert.text())
        self.assertTrue(self.dashboard.btn_qm_review.isHidden())

        # Check Inspector Status banner for Needs Review
        self.dashboard._update_inspector(r_review)
        self.assertFalse(self.dashboard.frame_qm_alert.isHidden())
        self.assertIn("Needs Review", self.dashboard.lbl_qm_alert.text())
        self.assertFalse(self.dashboard.btn_qm_review.isHidden())
        self.assertIn("14", self.dashboard.btn_qm_review.text())


if __name__ == "__main__":
    unittest.main()

