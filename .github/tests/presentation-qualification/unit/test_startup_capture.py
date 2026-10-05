import importlib.util
import json
import os
import unittest
from unittest import mock

CAPTURE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "runtime", "images", "gateway_files", "startup_capture.py")
)
SPEC = importlib.util.spec_from_file_location("startup_capture", CAPTURE_PATH)
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


class StartupCapture(unittest.TestCase):
    def test_report_excludes_exception_text_and_absolute_paths(self):
        try:
            raise RuntimeError("must-not-leak /private/path or local values")
        except RuntimeError as exc:
            encoded = capture._report(exc, exc.__traceback__)
        self.assertLessEqual(len(encoded), capture.MAX_REPORT_BYTES)
        text = encoded.decode("ascii")
        self.assertNotIn("must-not-leak", text)
        self.assertNotIn("/private/path", text)
        doc = capture.parse_report(text)
        self.assertEqual(doc["exception_type"], "RuntimeError")
        self.assertTrue(all("/" not in frame["file"] for frame in doc["frames"]))

    def test_module_not_found_reports_only_validated_public_module(self):
        exc = ModuleNotFoundError("secret detail must-not-leak")
        exc.name = "public.package"
        doc = json.loads(capture._report(exc, None))
        self.assertEqual(doc["modules"], ["other"])
        self.assertNotIn("must-not-leak", json.dumps(doc))

    def test_parser_rejects_unexpected_fields_and_unsafe_values(self):
        self.assertIsNone(capture.parse_report('{"version":1,"message":"no"}'))
        self.assertIsNone(capture.parse_report('{"version":1,"exception_type":"RuntimeError","causes":[],"modules":[],"frames":[{"file":"/tmp/x","line":1}]}'))
        self.assertEqual(capture.parse_report('{"version":1,"capture_error":true}'), {"capture_error": True})

    def test_zero_system_exit_does_not_capture(self):
        self.assertFalse(capture.should_capture_system_exit(None))
        self.assertFalse(capture.should_capture_system_exit(0))
        self.assertTrue(capture.should_capture_system_exit(1))

    def test_parser_requires_bounded_json_report(self):
        self.assertIsNone(capture.parse_report("x" * (capture.MAX_REPORT_BYTES + 1)))

    def test_parser_rejects_overlong_module(self):
        module = "a" * 81
        raw = json.dumps({"version": 1, "exception_type": "Error", "causes": [], "modules": [module], "frames": []})
        self.assertIsNone(capture.parse_report(raw))

    def test_main_exit_behavior_is_quiet(self):
        with mock.patch.object(capture, "runpy") as mocked_runpy, mock.patch.object(capture, "_capture"):
            mocked_runpy.run_path.side_effect = SystemExit(0)
            with self.assertRaises(SystemExit) as result:
                capture.main()
            self.assertEqual(result.exception.code, 0)
            mocked_runpy.run_path.side_effect = SystemExit(7)
            with self.assertRaises(SystemExit) as result:
                capture.main()
            self.assertEqual(result.exception.code, 7)
            mocked_runpy.run_path.side_effect = RuntimeError("private message")
            with self.assertRaises(SystemExit) as result:
                capture.main()
            self.assertEqual(result.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
