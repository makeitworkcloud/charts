import importlib.util
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "runtime/client/snapshot_diff.py"
SPEC = importlib.util.spec_from_file_location("snapshot_diff", SOURCE)
snapshot_diff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot_diff)


class SnapshotTests(unittest.TestCase):
    def load_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pods.tsv"
            path.write_text(text, encoding="utf-8")
            return snapshot_diff.load(path)

    def test_empty_snapshot(self):
        self.assertEqual(self.load_text(""), set())

    def test_metadata_tuple(self):
        self.assertEqual(self.load_text("pptx-jobs\tkernel-a\t1234-abcd\n"),
                         {("pptx-jobs", "kernel-a", "1234-abcd")})

    def test_malformed_and_duplicate_rows(self):
        for text in ("a\tb\n", "a\tb\t\n", '{"items":[]}\n',
                     "a\tb\t123\na\tb\t123\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load_text(text)

    def test_zero_mode_rejects_in_namespace_creation(self):
        pod = ("pptx-jobs", "unlabelled", "123")
        self.assertEqual(snapshot_diff.violations(set(), {pod}, "pptx-jobs", "zero"), {pod})

    def test_scope_mode_allows_only_fixture_namespace(self):
        inside = ("pptx-jobs", "kernel", "123")
        outside = ("default", "kernel", "456")
        self.assertEqual(snapshot_diff.violations(set(), {inside, outside}, "pptx-jobs", "scope"),
                         {outside})

    def test_uid_replacement_and_removal_detected(self):
        old = ("pptx-jobs", "kernel", "123")
        new = ("pptx-jobs", "kernel", "456")
        self.assertEqual(snapshot_diff.violations({old}, {new}, "pptx-jobs", "zero"), {old, new})

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            snapshot_diff.violations(set(), set(), "pptx-jobs", "invalid")
