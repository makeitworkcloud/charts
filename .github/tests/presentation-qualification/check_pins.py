#!/usr/bin/env python3
"""Fail-closed validator for pins.env. Exits 0 only when every pin is present,
non-pending, well formed, and internally consistent. Missing/pending pins exit
2, malformed or inconsistent pins exit 3."""

import re
import sys

HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST_IMAGE = re.compile(r"^[a-z0-9./_:~-]+@sha256:[0-9a-f]{64}$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
PIPVER = re.compile(r"^\d+(\.\d+)+[a-zA-Z0-9.+-]*$")

KEYS = {
    "EG_REVISION": HEX40,
    "NODE_BASE_IMAGE": DIGEST_IMAGE,
    "ENTERPRISE_GATEWAY": PIPVER,
    "JUPYTER_CLIENT": PIPVER,
    "IPYKERNEL": PIPVER,
    "PYZMQ": PIPVER,
    "PYCRYPTODOMEX": PIPVER,
    "KUBERNETES_PY": PIPVER,
    "JINJA2": PIPVER,
    "PYYAML": PIPVER,
    "REQUESTS": PIPVER,
    "WEBSOCKET_CLIENT": PIPVER,
    "PILLOW": PIPVER,
    "PPTXGENJS_VERSION": PIPVER,
    "KIND_VERSION": SEMVER,
    "KIND_SHA256": HEX64,
    "KIND_NODE_IMAGE": DIGEST_IMAGE,
    "KUBECTL_SOURCE": re.compile(r"^(pinned_download|runner_preinstalled)$"),
    "KUBECTL_VERSION": re.compile(r"^(unpinned|\d+\.\d+\.\d+)$"),
    "KUBECTL_SHA256": re.compile(r"^(unpinned|[0-9a-f]{64})$"),
}

PENDING_PREFIX = "PENDING"


def load(path):
    values = {}
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError("line %d: not KEY=VALUE" % lineno)
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key not in KEYS:
                raise ValueError("line %d: unknown key %s" % (lineno, key))
            if key in values:
                raise ValueError("line %d: duplicate key %s" % (lineno, key))
            values[key] = value
    return values


def cross_rules(values):
    errors = []
    if values["KUBECTL_SOURCE"] == "runner_preinstalled":
        if values["KUBECTL_VERSION"] != "unpinned" or values["KUBECTL_SHA256"] != "unpinned":
            errors.append("runner_preinstalled kubectl must leave version/sha as unpinned")
    if values["KUBECTL_SOURCE"] == "pinned_download":
        if values["KUBECTL_VERSION"] == "unpinned" or values["KUBECTL_SHA256"] == "unpinned":
            errors.append("pinned_download kubectl requires a real version and sha256")
    return errors


def validate(path):
    try:
        values = load(path)
    except (OSError, ValueError) as exc:
        return 3, ["unreadable or malformed pins file: %s" % exc]

    missing = [key for key in KEYS if key not in values]
    pending = [
        key
        for key, value in values.items()
        if not value or value.startswith(PENDING_PREFIX)
    ]
    if missing or pending:
        return 2, [
            "pins incomplete (parent must supply verified values): %s"
            % ", ".join(sorted(set(missing + pending)))
        ]

    malformed = [
        key
        for key, pattern in KEYS.items()
        if not pattern.match(values[key])
    ]
    if malformed:
        return 3, ["malformed pins: %s" % ", ".join(sorted(malformed))]

    inconsistent = cross_rules(values)
    if inconsistent:
        return 3, inconsistent
    return 0, []


def main(argv):
    if len(argv) != 2:
        print("usage: check_pins.py pins.env", file=sys.stderr)
        return 3
    code, errors = validate(argv[1])
    for error in errors:
        print(error, file=sys.stderr)
    if code == 0:
        print("pins complete and consistent: %d pins" % len(KEYS))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
