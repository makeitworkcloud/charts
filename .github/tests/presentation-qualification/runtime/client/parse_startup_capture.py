#!/usr/bin/env python3
"""Print only validated fields from the gateway's termination report."""

import importlib.util
import json
import os
import sys

fixture = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
capture_path = os.path.join(fixture, "runtime", "images", "gateway_files", "startup_capture.py")
spec = importlib.util.spec_from_file_location("startup_capture", capture_path)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def main():
    raw = sys.stdin.read(4097)
    report = capture.parse_report(raw)
    if report is None or report.get("capture_error"):
        print("GATEWAY_STARTUP_EXCEPTION CAPTURE_UNAVAILABLE")
        return
    print("GATEWAY_STARTUP_EXCEPTION type=%s" % report["exception_type"])
    for name in report["causes"]:
        print("GATEWAY_STARTUP_EXCEPTION cause=%s" % name)
    for module in report["modules"]:
        print("GATEWAY_STARTUP_EXCEPTION module=%s" % module)
    for frame in report["frames"]:
        print("GATEWAY_STARTUP_EXCEPTION frame=%s:%d" % (frame["file"], frame["line"]))


if __name__ == "__main__":
    main()
