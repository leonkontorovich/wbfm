"""
Launcher support for comparing against reference recordings: source tag/filter, neuron search ("n:AVAL, RIML")
ranked by match count, and the "find reference recordings with these '?' neurons" button.
"""
import os
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from qtpy.QtWidgets import QApplication
from qtpy.QtCore import Qt

from launch_gui import (
    WBFMRecordingDashboard, recording_source, clean_strain, parse_neuron_query, count_neuron_matches,
    is_drive_root, extract_metadata_for_project, read_exposure_time, acquisition_similarity, is_comparable,
    describe_acquisition, reference_patterns,
)

# Reference recordings are configured per machine; the tests use a fixed pattern regardless of local settings
_env_patch = mock.patch.dict(os.environ, {"WBFM_REFERENCE_PATTERNS": "reference_set"})


def setUpModule():
    _env_patch.start()


def tearDownModule():
    _env_patch.stop()


def make_record(name, root, annotated, qm=()):
    return {
        "name": name, "path": rf"{root}\{name}", "config_path": rf"{root}\{name}\project_config.yaml",
        "date": "2026-06-30", "strain": "ZIM2165", "has_masks": True, "has_tracks": True, "has_traces": True,
        "has_barlow": True, "tracked_count": 100, "annotated_count": len(annotated),
        "annotated_names": list(annotated) + list(qm), "annotated_details": [],
        "question_mark_count": len(qm), "question_mark_names": list(qm), "is_fully_processed": True,
        "missing_annotations": False, "is_recent": False,
    }


class TestHelpers(unittest.TestCase):
    def test_source_and_strain(self):
        self.assertEqual(recording_source({"path": r"Z:\neurobiology\zimmer\LeonK\Reference_set\w1"}), "Reference")
        self.assertEqual(recording_source({"path": r"Z:\neurobiology\zimmer\LeonK\Lit_immob\w1"}), "Mine")
        self.assertEqual(clean_strain("2026"), "")
        self.assertEqual(clean_strain("ZIM2165"), "ZIM2165")

    def test_reference_patterns_are_configurable(self):
        rec = {"path": r"Z:\data\Other_Lab_Set\w1"}
        with mock.patch.dict(os.environ, {"WBFM_REFERENCE_PATTERNS": " other_lab ; Z:\\refs ;"}):
            self.assertEqual(reference_patterns(), ["other_lab", "z:\\refs"])
            self.assertEqual(recording_source(rec), "Reference")
        with mock.patch.dict(os.environ, {"WBFM_REFERENCE_PATTERNS": ""}):
            self.assertEqual(reference_patterns(), [])
            self.assertEqual(recording_source(rec), "Mine")  # nothing configured: everything is your own

    def test_date_first_folder_names_have_no_fake_strain(self):
        meta = extract_metadata_for_project(r"C:\does\not\exist\2026-06-30_13-02_control_tet_worm1-2026-06-30")
        self.assertEqual(meta["strain"], "")

    def test_neuron_query(self):
        self.assertEqual(parse_neuron_query("n:AVAL, riml?,"), ["aval", "riml"])
        self.assertEqual(parse_neuron_query("neurons: AVAR"), ["avar"])
        self.assertIsNone(parse_neuron_query("AVAL"))
        self.assertEqual(parse_neuron_query("n:"), [])

    def test_uncertain_names_do_not_count_as_matches(self):
        rec = {"annotated_names": ["AVAL", "RIML?", "avar"]}
        self.assertEqual(count_neuron_matches(rec, ["aval", "riml", "avar", "smdd"]), 2)

    def test_drive_root(self):
        self.assertTrue(is_drive_root("C:\\"))
        self.assertTrue(is_drive_root("Z:"))
        self.assertFalse(is_drive_root(r"Z:\neurobiology"))


class TestAcquisitionSimilarity(unittest.TestCase):
    mine = {"exposure_time": 20.0, "num_volumes": 2500}
    same_rate_close = {"exposure_time": 20.0, "num_volumes": 2251}
    same_rate_short = {"exposure_time": 20.0, "num_volumes": 1000}
    fast_short = {"exposure_time": 12.0, "num_volumes": 1041}
    unknown = {}

    def test_ranking_prefers_same_frame_rate_then_closest_length(self):
        recs = [self.fast_short, self.same_rate_short, self.unknown, self.same_rate_close]
        ranked = sorted(recs, key=lambda r: acquisition_similarity(self.mine, r))
        self.assertEqual(ranked[0], self.same_rate_close)
        self.assertEqual(ranked[1], self.same_rate_short)
        self.assertEqual(set(map(id, ranked[2:])), {id(self.fast_short), id(self.unknown)})

    def test_comparable_needs_same_rate_and_similar_length(self):
        self.assertTrue(is_comparable(self.mine, self.same_rate_close))
        self.assertFalse(is_comparable(self.mine, self.same_rate_short))   # right rate, much shorter
        self.assertFalse(is_comparable(self.mine, self.fast_short))        # different frame rate
        self.assertFalse(is_comparable(self.mine, self.unknown))

    def test_describe(self):
        self.assertEqual(describe_acquisition(self.same_rate_close), "2251 vol · 20 ms")
        self.assertEqual(describe_acquisition({}), "")

    def test_read_exposure_time(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "project_config.yaml"), "w") as f:
                f.write("physical_units:\n  exposure_time: 12\n")
            self.assertEqual(read_exposure_time(d), 12.0)
            self.assertEqual(read_exposure_time(os.path.join(d, "project_config.yaml")), 12.0)
            self.assertIsNone(read_exposure_time(os.path.join(d, "missing.yaml")))


class TestDashboardReferenceFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.d = WBFMRecordingDashboard()
        self.d.stop_scanner()  # only the records inserted below
        self.d.table.setRowCount(0)
        self.d.records_by_path.clear()
        self.d.row_by_path.clear()
        mine = r"Z:\neurobiology\zimmer\LeonK\Lit_immob"
        ref_root = r"Z:\neurobiology\zimmer\LeonK\Reference_set"
        self.mine = make_record("mine_worm1", mine, ["AVAR"], qm=["AVAL?", "RIML?", "SMDD?"])
        self.i_two = make_record("ref_worm1", ref_root, ["AVAL", "RIML", "AVAR"])
        self.i_one = make_record("ref_worm2", ref_root, ["AVAL", "AVAR"])
        self.i_none = make_record("ref_worm3", ref_root, ["AVAR"])
        for rec in (self.mine, self.i_two, self.i_one, self.i_none):
            self.d._on_recording_discovered(dict(rec))

    def tearDown(self):
        self.d.stop_scanner()
        self.d.close()

    def visible_names(self):
        names = []
        for r in range(self.d.table.rowCount()):
            if not self.d.table.isRowHidden(r):
                names.append(self.d.table.item(r, 0).text())
        return names

    def test_source_filter(self):
        self.assertEqual(len(self.visible_names()), 4)
        self.d.source_combo.setCurrentText("Reference")
        self.assertEqual(len(self.visible_names()), 3)
        self.d.source_combo.setCurrentText("Mine")
        self.assertEqual(self.visible_names(), ["mine_worm1"])

    def test_reference_rows_are_tinted(self):
        for r in range(self.d.table.rowCount()):
            item = self.d.table.item(r, 0)
            color = item.foreground().color().name()
            if item.text().startswith("ref_"):
                self.assertEqual(color, "#61afef")
            else:
                self.assertEqual(color, "#ffffff")

    def test_neuron_search_ranks_by_matches_and_hides_the_rest(self):
        self.d.search_input.setText("n:AVAL, RIML")
        names = self.visible_names()
        self.assertEqual(names[0], "ref_worm1   ✓ 2/2")
        self.assertEqual(names[1], "ref_worm2   ✓ 1/2")
        self.assertEqual(len(names), 2)  # mine has only '?' versions, ref_worm3 has neither

    def test_leaving_neuron_search_restores_names(self):
        self.d.search_input.setText("n:AVAL")
        self.d.search_input.setText("")
        self.assertEqual(sorted(self.visible_names()), sorted(r["name"] for r in
                                                              (self.mine, self.i_two, self.i_one, self.i_none)))
        # Rows that did not match the query must get their plain name sort key back too
        keys = [self.d.table.item(r, 0).sort_key for r in range(self.d.table.rowCount())]
        self.assertTrue(all(isinstance(k, str) for k in keys), keys)

    def test_find_reference_button(self):
        self.d.table.selectRow([self.d.table.item(r, 0).data(Qt.UserRole)
                                for r in range(self.d.table.rowCount())].index(
            [k for k in self.d.records_by_path if k.endswith("mine_worm1")][0]))
        self.d._update_inspector(self.d.records_by_path[[k for k in self.d.records_by_path
                                                         if k.endswith("mine_worm1")][0]])
        self.assertTrue(self.d.btn_find_reference.isEnabled())
        self.d.btn_find_reference.click()
        self.assertEqual(self.d.source_combo.currentText(), "Reference")
        self.assertEqual(self.d.search_input.text(), "n:AVAL, RIML, SMDD")
        self.assertEqual(self.visible_names()[0], "ref_worm1   ✓ 2/3")

    def test_find_button_ranks_comparable_recordings_first_and_labels_them(self):
        ref_root = r"Z:\neurobiology\zimmer\LeonK\Reference_set"
        mine = r"Z:\neurobiology\zimmer\LeonK\Lit_immob"
        target = make_record("target", mine, ["AVAR"], qm=["AVAL?"])
        target.update(exposure_time=20.0, num_volumes=2500)
        far = make_record("far_fast", ref_root, ["AVAL"]); far.update(exposure_time=12.0, num_volumes=1041)
        near = make_record("near_same_rate", ref_root, ["AVAL"]); near.update(exposure_time=20.0, num_volumes=2251)
        for rec in (target, far, near):
            self.d._on_recording_discovered(dict(rec))
        self.d._update_inspector(self.d.records_by_path[[k for k in self.d.records_by_path if k.endswith("target")][0]])
        self.d.btn_find_reference.click()
        names = self.visible_names()
        self.assertTrue(names[0].startswith("near_same_rate"), names)
        self.assertIn("2251 vol · 20 ms · ≈ comparable", names[0])
        far_label = [n for n in names if n.startswith("far_fast")][0]
        self.assertIn("1041 vol · 12 ms", far_label)
        self.assertNotIn("comparable", far_label)
        # Clearing the search drops the similarity target
        self.d.search_input.setText("")
        self.assertIsNone(self.d._similarity_target)

    def test_button_disabled_without_question_marks(self):
        rec = self.d.records_by_path[[k for k in self.d.records_by_path if k.endswith("ref_worm1")][0]]
        self.d._update_inspector(rec)
        self.assertFalse(self.d.btn_find_reference.isEnabled())

    def test_drive_root_never_becomes_a_search_root(self):
        self.assertFalse([r for r in self.d.search_roots if is_drive_root(r)])


if __name__ == "__main__":
    unittest.main()
