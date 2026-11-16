"""
Tests for reviewing uncertain ('?') neuron IDs: NeuronNameEditor.accept/reject/correct/undo,
the atomic save, and the QuestionMarkReviewer queue logic. Headless (offscreen Qt), no napari viewer.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
from PyQt5.QtWidgets import QApplication

from wbfm.gui.utils.utils_gui import NeuronNameEditor
from wbfm.gui.utils.question_mark_reviewer import (
    QuestionMarkReviewer, ReferenceRecording, zscore, describe_trace, crop_window, best_window_start,
    trace_in_seconds)

_app = QApplication.instance() or QApplication(sys.argv)


def make_df():
    return pd.DataFrame({
        'Neuron ID': ['neuron_001', 'neuron_002', 'neuron_003', 'neuron_004'],
        'Finished?': [''] * 4,
        'ID1': ['AVAL?', 'neuron_002', 'RIML?', 'AVAR'],
        'ID2': [''] * 4,
        'Certainty': [0, 0, 1, 2],
        'Notes': ['', '', 'looks like RIMR', ''],
    })


def make_editor(filename=None):
    editor = NeuronNameEditor(neurons_to_id=None)
    editor.import_dataframe(make_df(), filename)
    return editor


class TestEditorReviewActions(unittest.TestCase):
    def setUp(self):
        self.editor = make_editor()
        self.events = []
        self.editor.annotation_updated.connect(lambda *a: self.events.append(a))

    def test_uncertain_neurons(self):
        self.assertEqual(self.editor.uncertain_neurons(), ['neuron_001', 'neuron_003'])

    def test_accept_strips_question_mark_and_raises_certainty(self):
        self.assertTrue(self.editor.accept_question_mark('neuron_001'))
        df = self.editor.df
        self.assertEqual(df.at[0, 'ID1'], 'AVAL')
        self.assertEqual(df.at[0, 'Certainty'], 1)
        self.assertEqual(self.events, [('neuron_001', 'AVAL?', 'AVAL')])
        self.assertEqual(self.editor.uncertain_neurons(), ['neuron_003'])

    def test_accept_never_lowers_certainty(self):
        self.editor.df.at[2, 'Certainty'] = 2
        self.editor.accept_question_mark('neuron_003')
        self.assertEqual(self.editor.df.at[2, 'Certainty'], 2)

    def test_accept_on_certain_neuron_is_noop(self):
        self.assertFalse(self.editor.accept_question_mark('neuron_004'))
        self.assertEqual(self.events, [])

    def test_reject_resets_to_unnamed_and_keeps_proposal_in_notes(self):
        self.assertTrue(self.editor.reject_question_mark('neuron_003'))
        df = self.editor.df
        self.assertEqual(df.at[2, 'ID1'], '')
        self.assertEqual(df.at[2, 'Certainty'], 0)
        self.assertEqual(df.at[2, 'Notes'], 'looks like RIMR; rejected RIML?')
        self.assertEqual(self.events, [('neuron_003', 'RIML?', '')])

    def test_correct_uses_new_name(self):
        self.assertTrue(self.editor.correct_question_mark('neuron_003', 'RIMR'))
        self.assertEqual(self.editor.df.at[2, 'ID1'], 'RIMR')
        self.assertFalse(self.editor.correct_question_mark('neuron_001', 'AVAL?'))  # still uncertain: refused
        self.assertFalse(self.editor.correct_question_mark('neuron_001', '  '))

    def test_undo_restores_everything(self):
        before = self.editor.df.copy()
        self.editor.reject_question_mark('neuron_003')
        self.editor.accept_question_mark('neuron_001')
        self.assertEqual(self.editor.undo_review_action(), 'neuron_001')
        self.assertEqual(self.editor.undo_review_action(), 'neuron_003')
        self.assertIsNone(self.editor.undo_review_action())
        pd.testing.assert_frame_equal(self.editor.df, before)

    def test_table_stays_in_sync_with_dataframe(self):
        self.editor.accept_question_mark('neuron_001')
        id_col = self.editor.manual_id_column_idx
        self.assertEqual(self.editor.model.item(0, id_col).text(), 'AVAL')


class TestSave(unittest.TestCase):
    def test_atomic_save_roundtrip_and_no_rewrite_on_open(self):
        with tempfile.TemporaryDirectory() as d:
            fname = str(Path(d) / 'manual_annotation.xlsx')
            editor = make_editor(fname)  # file does not exist -> created
            self.assertTrue(os.path.exists(fname))

            # Edit externally; opening a project again must NOT overwrite it
            df = pd.read_excel(fname)
            df.loc[0, 'Notes'] = 'edited in excel'
            df.to_excel(fname, index=False)
            make_editor(fname)
            self.assertEqual(pd.read_excel(fname).loc[0, 'Notes'], 'edited in excel')

            editor.accept_question_mark('neuron_001')
            self.assertTrue(editor.save_df_to_disk(also_save_h5=False))
            self.assertEqual(pd.read_excel(fname).loc[0, 'ID1'], 'AVAL')
            self.assertFalse([f for f in os.listdir(d) if '.tmp' in f], "temp file left behind")

    def test_failed_save_reports_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            fname = str(Path(d) / 'manual_annotation.xlsx')
            editor = make_editor(fname)
            import wbfm.gui.utils.utils_gui as ug
            real_replace = os.replace
            ug.os.replace = MagicMock(side_effect=PermissionError("locked by Excel"))
            try:
                self.assertFalse(editor.save_df_to_disk(also_save_h5=False))
            finally:
                ug.os.replace = real_replace
            self.assertIn("locked", editor.last_save_error)
            self.assertFalse([f for f in os.listdir(d) if '.tmp' in f])


class TestReviewer(unittest.TestCase):
    def setUp(self):
        self.editor = make_editor()
        self.selected = []
        self.reviewer = QuestionMarkReviewer(self.editor, project_data=None, select_neuron=self.selected.append)

    def test_opening_does_not_select(self):
        self.assertEqual(self.selected, [])
        self.assertEqual(self.reviewer.queue, ['neuron_001', 'neuron_003'])

    def test_accept_advances_to_next_and_selects_it(self):
        self.reviewer.accept_current()
        self.assertEqual(self.editor.df.at[0, 'ID1'], 'AVAL')
        self.assertEqual(self.reviewer.current, 'neuron_003')
        self.assertEqual(self.selected, ['neuron_003'])

    def test_skip_and_back_wrap_around(self):
        self.reviewer.skip()
        self.assertEqual(self.reviewer.current, 'neuron_003')
        self.reviewer.skip()
        self.assertEqual(self.reviewer.current, 'neuron_001')
        self.reviewer.previous()
        self.assertEqual(self.reviewer.current, 'neuron_003')

    def test_finish_and_undo(self):
        self.reviewer.reject_current()
        self.reviewer.reject_current()
        self.assertIsNone(self.reviewer.current)
        self.assertIn("Nothing left", self.reviewer.progress_label.text())
        self.reviewer.undo()
        self.assertEqual(self.reviewer.current, 'neuron_003')

    def test_correct_from_text_box(self):
        self.reviewer.correct_edit.setText('AVAR2')
        self.reviewer.correct_current()
        self.assertEqual(self.editor.df.at[0, 'ID1'], 'AVAR2')
        self.assertEqual(self.reviewer.counts['corrected'], 1)

    def test_selection_failure_does_not_break_review(self):
        self.reviewer.select_neuron = MagicMock(side_effect=ValueError("not in dropdown"))
        self.reviewer.skip()
        self.assertEqual(self.reviewer.current, 'neuron_003')


class TestReference(unittest.TestCase):
    def test_reference_lookup_ignores_uncertain_ids(self):
        dat = MagicMock()
        dat.neuron_name_to_manual_id_mapping.return_value = {'AVAL': 'neuron_010', 'RIML?': 'neuron_011'}
        ref = ReferenceRecording(dat)
        self.assertTrue(ref.has('AVAL'))
        self.assertFalse(ref.has('RIML?'))
        dat.neuron_name_to_manual_id_mapping.assert_called_once_with(
            confidence_threshold=0, flip_names_and_ids=True, remove_unnamed_neurons=True)

    def test_zscore(self):
        z = zscore([1, 2, 3, np.nan])
        self.assertAlmostEqual(np.nanmean(z), 0)
        self.assertAlmostEqual(np.nanstd(z), 1)
        self.assertTrue(np.all(zscore([5, 5, 5]) == 0))


class TestIdTransferMerge(unittest.TestCase):
    """ProjectData methods called on a lightweight stand-in (no real project needed)"""

    def setUp(self):
        from wbfm.utils.projects.finished_project_data import ProjectData
        self.PD = ProjectData
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fname = str(Path(self.tmp.name) / 'transfer.xlsx')
        self.fake = MagicMock()
        self.fake.id_transfer_annotation_fname.return_value = self.fname

    def default_df(self):
        df = make_df()[['Neuron ID', 'Finished?', 'ID1', 'ID2', 'Certainty', 'Notes']].copy()
        df['ID1'] = df['Neuron ID']
        df['Certainty'] = 0
        df['Notes'] = ''
        return df

    def test_merge_copies_proposals_only_for_matching_neurons(self):
        pd.DataFrame({'neuron id': ['neuron_002', 'neuron_004', 'neuron_999'],
                      'ID1': ['SMDD?', 'RMED', 'X'], 'Certainty': [1, 2, 2]}).to_excel(self.fname, index=False)
        out = self.PD._merge_id_transfer_proposals(self.fake, self.default_df())
        self.assertEqual(list(out['ID1']), ['neuron_001', 'SMDD?', 'neuron_003', 'RMED'])
        self.assertEqual(list(out['Certainty']), [0, 1, 0, 2])
        self.assertEqual(len(out), 4)  # unknown neuron_999 not added

    def test_merge_without_usable_output_returns_input(self):
        df = self.default_df()
        self.fake.id_transfer_annotation_fname.return_value = None
        pd.testing.assert_frame_equal(self.PD._merge_id_transfer_proposals(self.fake, df), df)
        pd.DataFrame({'foo': [1]}).to_excel(self.fname, index=False)
        self.fake.id_transfer_annotation_fname.return_value = self.fname
        pd.testing.assert_frame_equal(self.PD._merge_id_transfer_proposals(self.fake, df), df)

    def test_blank_detection(self):
        blank = self.PD._annotations_are_blank
        df = self.default_df()
        self.assertTrue(blank(df))
        df.loc[0, 'ID1'] = 'AVAL'
        self.assertFalse(blank(df))
        df = self.default_df()
        df.loc[1, 'Notes'] = 'rejected AVAL?'  # all proposals rejected earlier: must not be re-imported
        self.assertFalse(blank(df))
        df = self.default_df()
        df.loc[2, 'Certainty'] = 1
        self.assertFalse(blank(df))


class TestComparisonPlot(unittest.TestCase):
    """Recordings differ in length and frame rate; the comparison must look complete either way"""

    @staticmethod
    def fake_project(n_frames, fps, nan_fraction=0.0, ids=None):
        dat = MagicMock()
        dat._trace_plotter = "explorer's own plotter"

        def calc(neuron_name, **kw):
            y = np.sin(np.arange(n_frames) / 20.0)
            y[: int(nan_fraction * n_frames)] = np.nan
            dat._trace_plotter = "replaced by calculate_traces"
            return np.arange(n_frames), y

        dat.calculate_traces.side_effect = calc
        dat.physical_unit_conversion.volumes_per_second = fps
        dat.num_frames = n_frames
        dat.project_dir = r"Z:\\Itamar\\worm3"
        dat.neuron_name_to_manual_id_mapping.return_value = ids or {'AVAL': 'ref_010', 'AVAR': 'ref_011'}
        return dat

    def make_reviewer(self, ref_frames=1041, ref_fps=3.47, ref_nan=0.0):
        editor = make_editor()
        reviewer = QuestionMarkReviewer(editor, project_data=self.fake_project(1250, 1.7),
                                        select_neuron=lambda n: None)
        reviewer.set_reference(ReferenceRecording(self.fake_project(ref_frames, ref_fps, ref_nan)))
        return reviewer

    def plotted_extents(self, reviewer):
        lines = [l for ax in reviewer.figure.axes for l in ax.get_lines()]
        return [(float(l.get_xdata()[0]), float(l.get_xdata()[-1])) for l in lines]

    def test_default_is_a_real_time_window_of_the_longer_recording(self):
        r = self.make_reviewer()  # mine 735 s, reference 300 s
        self.assertTrue(r.window_checkbox.isChecked())
        (m0, m1), (r0, r1) = self.plotted_extents(r)
        self.assertAlmostEqual(r0, 0.0)
        self.assertAlmostEqual(r1, 1040 / 3.47, places=3)      # reference untouched, true speed
        self.assertAlmostEqual(m0, 0.0, places=1)
        self.assertAlmostEqual(m1, 1040 / 3.47, delta=1.0)    # mine cut to the same length
        self.assertIn("showing 0", r.figure.axes[0].get_legend().get_texts()[0].get_text())

    def test_slider_moves_the_window_without_changing_its_length(self):
        r = self.make_reviewer()
        r.window_slider.setValue(1000)
        (m0, m1), _ = self.plotted_extents(r)
        self.assertAlmostEqual(m1 - m0, 1040 / 3.47, delta=1.0)
        text = r.figure.axes[0].get_legend().get_texts()[0].get_text()
        self.assertIn("showing 435–735 s", text.replace("-", "–"))

    def test_window_off_shows_both_whole_recordings_in_real_time(self):
        r = self.make_reviewer()
        r.window_checkbox.setChecked(False)
        (m0, m1), (r0, r1) = self.plotted_extents(r)
        self.assertAlmostEqual(m1, 1249 / 1.7, places=3)
        self.assertAlmostEqual(r1, 1040 / 3.47, places=3)
        self.assertFalse(r.window_slider.isEnabled())

    def test_legend_does_not_name_the_reference_recording(self):
        r = self.make_reviewer()
        labels = " ".join(t.get_text() for t in r.figure.axes[0].get_legend().get_texts())
        self.assertIn("reference: AVAL", labels)
        self.assertNotIn("Itamar", labels)
        self.assertNotIn("worm3", labels)

    def test_best_window_finds_the_matching_stretch(self):
        t_long = np.arange(0, 600.0, 0.5)
        pattern = np.sin(t_long / 6.0) * np.exp(-((t_long - 400) / 40.0) ** 2)  # a bump around 360-440 s
        t_short = np.arange(0, 100.0, 0.5)
        short = np.sin((t_short + 350) / 6.0) * np.exp(-((t_short + 350 - 400) / 40.0) ** 2)
        start, r = best_window_start(t_long, pattern + 0.01 * np.cos(t_long), t_short, short)
        self.assertAlmostEqual(start, 350, delta=6)
        self.assertGreater(r, 0.95)

    def test_status_warns_about_different_frame_rate_and_length(self):
        r = self.make_reviewer()  # mine 1.7 vol/s x 1250, reference 3.47 vol/s x 1041
        status = r.reference_status.text()
        self.assertIn("1041 volumes at 3.47/s = 300 s", status)
        self.assertIn("different frame rate", status)
        self.assertIn("very different length", status)

    def test_status_is_quiet_for_a_comparable_reference(self):
        r = self.make_reviewer(ref_frames=1250, ref_fps=1.7)
        self.assertNotIn("⚠", r.reference_status.text())

    def test_best_window_button_moves_slider(self):
        r = self.make_reviewer()
        r.jump_to_best_window()
        self.assertIn("best r", r.window_label.text())

    def test_crop_window(self):
        t, y = crop_window(np.arange(10.0) + 100, np.arange(10.0), start=3, length=4)
        np.testing.assert_allclose(t, [0, 1, 2, 3, 4])
        np.testing.assert_allclose(y, [3, 4, 5, 6, 7])

    def test_legend_reports_duration_and_missing_data(self):
        r = self.make_reviewer(ref_nan=0.16)
        labels = [t.get_text() for t in r.figure.axes[0].get_legend().get_texts()]
        self.assertTrue(any(l.startswith("this: neuron_001 (735 s)") for l in labels), labels)
        self.assertTrue(any("300 s, 16% missing" in l for l in labels), labels)

    def test_stacked_mode_plots_both(self):
        r = self.make_reviewer()
        r.overlay_checkbox.setChecked(False)
        self.assertEqual(len(r.figure.axes), 2)

    def test_case_insensitive_lookup_and_suggestions(self):
        ref = ReferenceRecording(self.fake_project(100, 1.0))
        self.assertEqual(ref.lookup('aval'), 'AVAL')
        self.assertIsNone(ref.lookup('RIML'))
        self.assertEqual(ref.similar('AVAB'), ['AVAL', 'AVAR'])

    def test_missing_neuron_explains_itself(self):
        r = self.make_reviewer()
        r.skip()  # neuron_003 -> RIML?, which the reference lacks
        texts = [t.get_text() for t in r.figure.axes[0].texts]
        self.assertTrue(any("'RIML' is not annotated" in t for t in texts), texts)

    def test_trace_calculation_does_not_disturb_the_explorers_plotter(self):
        dat = self.fake_project(100, 1.0)
        trace_in_seconds(dat, 'neuron_001')
        self.assertEqual(dat._trace_plotter, "explorer's own plotter")

    def test_reference_traces_are_cached(self):
        dat = self.fake_project(100, 1.0)
        ref = ReferenceRecording(dat)
        ref.trace('AVAL')
        ref.trace('aval')
        self.assertEqual(dat.calculate_traces.call_count, 1)

    def test_helpers(self):
        self.assertEqual(describe_trace([0, 300], [1, np.nan]), "300 s, 50% missing")
        self.assertEqual(describe_trace([0, 300], [1, 2]), "300 s")


class TestDeclutteredGui(unittest.TestCase):
    def test_collapsible_section_only_toggles_visibility(self):
        from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QWidget, QPushButton
        from PyQt5.QtCore import Qt
        from wbfm.gui.utils.napari_trace_explorer import NapariTraceExplorer
        host = QWidget()
        fake = MagicMock()
        fake.verticalLayout = QVBoxLayout(host)
        box = QGroupBox("Options")
        inner = QPushButton("x", box)
        inner.setEnabled(False)  # the explorer enables/disables buttons itself; collapsing must not change that
        NapariTraceExplorer._add_collapsible_section(fake, box, "Options", expanded=False)
        host.show()
        button = fake.verticalLayout.itemAt(0).widget()
        self.assertTrue(box.isHidden())
        self.assertEqual(box.title(), "")
        button.setChecked(True)
        self.assertFalse(box.isHidden())
        button.setChecked(False)
        self.assertTrue(box.isHidden())
        self.assertFalse(inner.isEnabled())

    def test_editor_in_tabified_docks_comes_to_front_on_jump(self):
        from PyQt5.QtWidgets import QMainWindow, QDockWidget, QLabel
        from PyQt5.QtCore import Qt
        editor = make_editor()
        win = QMainWindow()
        d1, d2 = QDockWidget("main", win), QDockWidget("names", win)
        d1.setWidget(QLabel("controls"))
        d2.setWidget(editor)
        win.addDockWidget(Qt.RightDockWidgetArea, d1)
        win.addDockWidget(Qt.RightDockWidgetArea, d2)
        win.tabifyDockWidget(d1, d2)
        d1.raise_()
        win.show()
        _app.processEvents()
        editor._bring_to_front()
        _app.processEvents()
        self.assertTrue(d2.isVisible())
        # The four helper lists live in tabs under the table
        self.assertEqual(editor.listTabs.count(), 4)
        self.assertIs(editor.listTabs.widget(3), editor.questionMarkList)


if __name__ == '__main__':
    unittest.main()
