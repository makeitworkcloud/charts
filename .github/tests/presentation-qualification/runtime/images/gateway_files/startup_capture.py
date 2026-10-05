#!/usr/bin/env python3
"""Run the installed Enterprise Gateway entry point with bounded safe capture."""

import json
import os
import re
import runpy
import sys
import traceback
import builtins

VENDOR_ENTRY = "/opt/venv/bin/jupyter-enterprisegateway"
REPORT_PATH = "/dev/termination-log"
PUBLIC_FILES = {"startup_capture.py", "jupyter-enterprisegateway", "enterprisegatewayapp.py", "mixins.py", "serverapp.py", "logging.py", "application.py", "configurable.py", "__init__.py", "runpy.py", "remotemanager.py", "web.py"}
PUBLIC_MODULE_ROOTS = {"enterprise_gateway", "jupyter_server", "jupyter_client", "jupyter_core", "traitlets", "tornado", "zmq", "kubernetes", "jinja2", "yaml", "requests", "websocket", "PIL", "Crypto", "Cryptodome"}
PUBLIC_TYPES = {name for name, value in vars(builtins).items() if isinstance(value, type) and issubclass(value, BaseException)} | {"unknown", "TraitError"}
MAX_REPORT_BYTES = 2048
SAFE_ATOM = re.compile(r"\A[A-Za-z0-9_.-]{1,80}\Z", re.ASCII)
SAFE_MODULE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z", re.ASCII)


def _safe_atom(value, default="unknown"):
    if isinstance(value, str) and value.isascii() and SAFE_ATOM.fullmatch(value):
        return value
    return default


def _report(exc, tb):
    frames = []
    for frame in traceback.extract_tb(tb)[-8:]:
        filename = os.path.basename(frame.filename)
        frames.append({"file": filename if filename in PUBLIC_FILES else "other", "line": max(0, int(frame.lineno))})
    types = []
    modules = []
    seen = set()
    current = exc
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        types.append(type(current).__name__ if type(current).__name__ in PUBLIC_TYPES else "unknown")
        if isinstance(current, ModuleNotFoundError):
            name = current.name
            if isinstance(name, str) and name.isascii() and len(name) <= 80 and SAFE_MODULE.fullmatch(name):
                modules.append(name.split(".")[0] if name.split(".")[0] in PUBLIC_MODULE_ROOTS else "other")
        current = current.__cause__ if current.__cause__ is not None else current.__context__
    report = {
        "version": 1,
        "exception_type": types[0] if types else "unknown",
        "causes": types[1:],
        "modules": modules[:4],
        "frames": frames,
    }
    encoded = json.dumps(report, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(encoded) > MAX_REPORT_BYTES:
        report["frames"] = report["frames"][-4:]
        report["modules"] = []
        encoded = json.dumps(report, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(encoded) > MAX_REPORT_BYTES:
        return b'{"version":1,"capture_error":true}'
    return encoded


def _capture(exc, tb):
    try:
        # Kubernetes v1.33.4 kubelet creates this termination file writable for
        # non-root containers; File policy exposes this bounded report, not logs.
        with open(REPORT_PATH, "w", encoding="ascii") as handle:
            handle.write(_report(exc, tb).decode("ascii"))
    except BaseException:
        try:
            with open(REPORT_PATH, "w", encoding="ascii") as handle:
                handle.write('{"version":1,"capture_error":true}')
        except BaseException:
            pass


def should_capture_system_exit(code):
    return code not in (None, 0)


def main():
    sys.argv[0] = VENDOR_ENTRY
    try:
        runpy.run_path(VENDOR_ENTRY, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if should_capture_system_exit(code):
            _capture(exc, exc.__traceback__)
        if code is None or code == 0:
            raise SystemExit(0)
        if isinstance(code, int):
            raise SystemExit(code)
        raise SystemExit(1)
    except BaseException as exc:
        _capture(exc, exc.__traceback__)
        raise SystemExit(1)


def parse_report(raw):
    """Validate and return only the source-authored, bounded report schema."""
    if not isinstance(raw, str) or len(raw.encode("utf-8", "ignore")) > MAX_REPORT_BYTES:
        return None
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(doc, dict) or type(doc.get("version")) is not int or doc.get("version") != 1:
        return None
    if set(doc) == {"version", "capture_error"} and doc.get("capture_error") is True:
        return {"capture_error": True}
    if set(doc) != {"version", "exception_type", "causes", "modules", "frames"}:
        return None
    exception_type = doc["exception_type"]
    causes, modules, frames = doc["causes"], doc["modules"], doc["frames"]
    if not isinstance(exception_type, str) or exception_type not in PUBLIC_TYPES:
        return None
    if not isinstance(causes, list) or len(causes) > 3 or any(not isinstance(x, str) or x not in PUBLIC_TYPES for x in causes):
        return None
    if not isinstance(modules, list) or len(modules) > 4 or any(not isinstance(x, str) or x not in PUBLIC_MODULE_ROOTS | {"other"} for x in modules):
        return None
    if any(len(x) > 80 for x in modules):
        return None
    if not isinstance(frames, list) or len(frames) > 8:
        return None
    safe_frames = []
    for frame in frames:
        if not isinstance(frame, dict) or set(frame) != {"file", "line"}:
            return None
        if not isinstance(frame["file"], str) or frame["file"] not in PUBLIC_FILES | {"other"}:
            return None
        if not isinstance(frame["line"], int) or isinstance(frame["line"], bool) or frame["line"] < 0:
            return None
        safe_frames.append(frame)
    return {"exception_type": exception_type, "causes": causes, "modules": modules, "frames": safe_frames}


if __name__ == "__main__":
    main()
