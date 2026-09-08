#!/usr/bin/env python3
import pathlib
import tempfile
import unittest
import zipfile

from apk_repro_diff import describe


class ApkReproDiffTests(unittest.TestCase):
    def test_reports_changed_and_content_equivalent_renamed_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            left = pathlib.Path(directory) / "left.apk"
            right = pathlib.Path(directory) / "right.apk"
            with zipfile.ZipFile(left, "w") as archive:
                archive.writestr("same", b"same")
                archive.writestr("changed", b"left")
                archive.writestr("guid-a", b"payload")
            with zipfile.ZipFile(right, "w") as archive:
                archive.writestr("same", b"same")
                archive.writestr("changed", b"right")
                archive.writestr("guid-b", b"payload")
            report = describe(left, right)
            self.assertEqual(["changed"], [item["name"] for item in report["common_entry_differences"]])
            self.assertEqual("guid-a", report["renamed_equal_content_entries"][0]["left_name"])
            self.assertEqual("guid-b", report["renamed_equal_content_entries"][0]["right_name"])
            self.assertEqual([], report["unmatched_left_entries"])
            self.assertEqual([], report["unmatched_right_entries"])


if __name__ == "__main__":
    unittest.main()
