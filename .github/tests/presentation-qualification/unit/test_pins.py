import os
import subprocess
import sys
import tempfile
import unittest

CHECK_PINS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "check_pins.py")
)

VALID = """\
EG_REVISION=0344929cbca688440ba1bc8f5faa074fe54bd595
NODE_BASE_IMAGE=docker.io/library/node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c
ENTERPRISE_GATEWAY=3.3.0
JUPYTER_CLIENT=6.1.12
IPYKERNEL=6.29.5
PYZMQ=24.0.1
PYCRYPTODOMEX=3.20.0
KUBERNETES_PY=31.0.0
JINJA2=3.1.6
PYYAML=6.0.3
REQUESTS=2.32.5
WEBSOCKET_CLIENT=1.8.0
PILLOW=11.3.0
PPTXGENJS_VERSION=4.0.1
KIND_VERSION=0.30.0
KIND_SHA256=517ab7fc89ddeed5fa65abf71530d90648d9638ef0c4cde22c2c11f8097b8889
KIND_NODE_IMAGE=kindest/node:v1.33.4@sha256:25a6018e48dfcaee478f4a59af81157a437f15e6e140bf103f85a2e7cd0cbbf2
KUBECTL_SOURCE=runner_preinstalled
KUBECTL_VERSION=unpinned
KUBECTL_SHA256=unpinned
"""


def run_check(content):
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
        handle.write(content)
        path = handle.name
    try:
        proc = subprocess.run(
            [sys.executable, CHECK_PINS, path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return proc.returncode, proc.stdout, proc.stderr
    finally:
        os.unlink(path)


def with_value(key, value):
    lines = []
    for line in VALID.splitlines():
        if line.startswith(key + "="):
            lines.append("%s=%s" % (key, value))
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


class ValidPins(unittest.TestCase):
    def test_valid_configuration_passes(self):
        code, out, err = run_check(VALID)
        self.assertEqual(code, 0, err)
        self.assertIn("pins complete", out)

    def test_pinned_download_kubectl_valid(self):
        content = VALID.replace("KUBECTL_SOURCE=runner_preinstalled", "KUBECTL_SOURCE=pinned_download")
        content = content.replace("KUBECTL_VERSION=unpinned", "KUBECTL_VERSION=1.33.0")
        content = content.replace("KUBECTL_SHA256=unpinned", "KUBECTL_SHA256=" + "a" * 64)
        code, _, err = run_check(content)
        self.assertEqual(code, 0, err)

    def test_cni_keys_are_rejected(self):
        code, _, err = run_check(VALID + "CNI_NP_ENFORCED=false\n")
        self.assertEqual(code, 3, err)


class PendingOrMissing(unittest.TestCase):
    def test_pending_value_fails_with_key_named(self):
        code, _, err = run_check(with_value("KIND_VERSION", "PENDING_PARENT_PIN"))
        self.assertEqual(code, 2)
        self.assertIn("KIND_VERSION", err)

    def test_missing_key_fails(self):
        content = "\n".join(line for line in VALID.splitlines() if not line.startswith("PILLOW="))
        code, _, err = run_check(content)
        self.assertEqual(code, 2)
        self.assertIn("PILLOW", err)

    def test_empty_value_fails(self):
        code, _, err = run_check(with_value("EG_REVISION", ""))
        self.assertEqual(code, 2)


class Malformed(unittest.TestCase):
    def test_bad_sha256(self):
        code, _, err = run_check(with_value("KIND_SHA256", "zz" * 32))
        self.assertEqual(code, 3)

    def test_bad_digest_image(self):
        code, _, err = run_check(with_value("NODE_BASE_IMAGE", "node:22"))
        self.assertEqual(code, 3)

    def test_unknown_key_rejected(self):
        code, _, err = run_check(VALID + "TOTALLY_NEW_PIN=1\n")
        self.assertEqual(code, 3)

    def test_duplicate_key_rejected(self):
        code, _, err = run_check(VALID + "KIND_VERSION=0.30.0\n")
        self.assertEqual(code, 3)

    def test_vulnerable_jinja2_not_pinned_in_fixture(self):
        with open(
            os.path.join(os.path.dirname(__file__), "..", "pins.env"), encoding="utf-8"
        ) as handle:
            pins = handle.read()
        self.assertNotIn("JINJA2=3.1.4", pins)
        self.assertIn("JINJA2=3.1.6", pins)


class CrossRules(unittest.TestCase):
    def test_runner_kubectl_must_stay_unpinned(self):
        content = with_value("KUBECTL_VERSION", "1.33.0")
        code, _, err = run_check(content)
        self.assertEqual(code, 3)
        self.assertIn("runner_preinstalled", err)

    def test_pinned_download_requires_real_values(self):
        content = with_value("KUBECTL_SOURCE", "pinned_download")
        code, _, err = run_check(content)
        self.assertEqual(code, 3)
        self.assertIn("pinned_download", err)


if __name__ == "__main__":
    unittest.main()
