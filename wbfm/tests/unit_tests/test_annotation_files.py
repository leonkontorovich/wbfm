"""Which manual-annotation file of a project is current (shared by the dashboard and `go check-ids`)"""
import os
import tempfile
import time
import unittest

from wbfm.utils.projects.annotation_files import (
    ANNOTATION_CANDIDATES, annotation_excel_file, newest_annotation_file,
)


class TestAnnotationFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def make(self, rel, age_s=0.0):
        path = os.path.join(self.proj, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("x")
        t = time.time() - age_s
        os.utime(path, (t, t))
        return path

    def test_no_files(self):
        self.assertIsNone(newest_annotation_file(self.proj))
        self.assertIsNone(annotation_excel_file(self.proj))

    def test_newest_file_wins_and_excel_follows_it(self):
        self.make("3-tracking/manual_annotation/manual_annotation.xlsx", age_s=1000)
        newer = self.make("3-tracking/id_transfer_output/hungarian/manual_annotation.xlsx", age_s=10)
        self.assertEqual(newest_annotation_file(self.proj), newer)
        # 'Open in Excel' must open the same file the counts came from
        self.assertEqual(annotation_excel_file(self.proj), newer)

    def test_h5_newest_opens_its_excel_sibling(self):
        sibling = self.make("3-tracking/manual_annotation/manual_annotation.xlsx", age_s=1000)
        self.make("3-tracking/hungarian/manual_annotation.xlsx", age_s=500)
        h5 = self.make("3-tracking/manual_annotation/manual_annotation.h5", age_s=1)
        self.assertEqual(newest_annotation_file(self.proj), h5)
        self.assertEqual(annotation_excel_file(self.proj), sibling)

    def test_h5_without_sibling_falls_back_to_priority_order(self):
        h5 = self.make("3-tracking/manual_annotation/manual_annotation.h5", age_s=1)
        later = self.make("manual_annotation.xlsx", age_s=100)
        first = self.make("3-tracking/hungarian/manual_annotation.xlsx", age_s=500)
        self.assertEqual(newest_annotation_file(self.proj), h5)
        self.assertEqual(annotation_excel_file(self.proj), first)
        self.assertLess(ANNOTATION_CANDIDATES.index("3-tracking/hungarian/manual_annotation.xlsx"),
                        ANNOTATION_CANDIDATES.index("manual_annotation.xlsx"))
        self.assertNotEqual(annotation_excel_file(self.proj), later)

    def test_excel_only_mode_ignores_h5(self):
        self.make("3-tracking/manual_annotation/manual_annotation.h5", age_s=1)
        xlsx = self.make("3-tracking/hungarian/manual_annotation.xlsx", age_s=100)
        self.assertEqual(newest_annotation_file(self.proj, excel_only=True), xlsx)


if __name__ == "__main__":
    unittest.main()
