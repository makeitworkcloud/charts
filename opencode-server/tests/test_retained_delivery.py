import json
import os
import subprocess
import unittest

import yaml

CHART = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class RetainedDeliveryContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["helm", "template", "test", CHART], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc is not None]
        cls.data = next(doc for doc in docs if doc["kind"] == "ConfigMap")["data"]
        cls.config = json.loads(cls.data["opencode.json"])

    def policy(self, name):
        return " ".join(self.data["skills-" + name + "-SKILL.md"].split())

    def test_exact_permissions_without_new_native_grants(self):
        expected = {name: {"/artifacts/*": "allow", "/repos/*": "allow"} for name in ("external_directory", "glob", "grep", "list", "read", "edit")}
        expected.update({"agent-pipe_download_artifact": "ask", "agent-pipe_inspect_artifact": "allow", "agent-pipe_remove_artifact": "ask", "agent-pipe_upload_artifact": "ask", "agent-pipe_verify_download": "allow"})
        self.assertEqual(self.config["permission"], expected)
        self.assertEqual(self.config["mcp"]["agent-pipe"], {"type": "remote", "url": "http://agent-pipe-uploader.opencode.svc:8080/mcp", "enabled": True, "oauth": False})

    def test_separate_policy_selection_and_existing_get(self):
        text = self.policy("s3-presigned-file-delivery")
        for marker in (
            "Ordinary new artifacts: profile `agent-pipe`",
            "deliveries/<session-id>/<artifact-id>/<filename>", "retention_days: 1",
            "Retained generated decks: profile `agent-presentations`", "retention_days: 90",
            "Do not require presentation-specific lifecycle, SlideSpeak, upload or cleanup prerequisites for a generic existing-object GET",
            "Without a prior digest, full GET verification establishes the current observed identity, NOT historical identity",
            "For existing GETs do not invent/reset retention", "[Download artifact](url)",
        ):
            self.assertIn(marker, text)

    def test_requested_format_preserves_pptx_or_pdf(self):
        text = self.policy("s3-presigned-file-delivery")
        self.assertIn("`response_format: powerpoint` selects `pptx`", text)
        self.assertIn("`response_format: pdf` selects `pdf`", text)
        self.assertIn("Never infer format from an untrusted filename/URL or expand bytes", text)
        for name in ("cloud-artifact-transfer", "career-external-documents", "s3-presigned-file-delivery"):
            text = self.policy(name)
            self.assertIn("presentation.<ext>", text)
            self.assertIn("100 MiB", text)
            self.assertNotIn("presentation.pptx", text)

    def test_capacity_uncertainty_is_not_unconditional_stop(self):
        text = self.policy("cloud-artifact-transfer")
        for marker in (
            "1 GiB shared artifact PVC", "no per-session reservation or quota",
            "at most one deck per request", "transfer sequentially",
            "Stop on known insufficient capacity", "report lack of assurance",
            "uncertainty alone does not require an unconditional stop",
            "ENOSPC/write failure fails the download and cleans its partial temporary file",
            "No new capacity tool", "no automatic deletion",
        ):
            if marker == "no automatic deletion":
                self.assertIn("or automatic deletion is added", text)
            else:
                self.assertIn(marker, text)

    def test_temporary_vendor_get_is_explicit_bounded_exception(self):
        text = self.policy("career-external-documents")
        for marker in (
            "retention is unavailable or declined", "slidespeak_downloadPresentation",
            "[Download artifact](url)", "NEVER PUT URLs", "TEMPORARY, NOT ARCHIVED",
            "expiry is unspecified unless the tool reports it", "do not promise 900 seconds",
            "SAME `request_id`, not regeneration", "archive INCOMPLETE",
            "retry once sequentially",
        ):
            self.assertIn(marker, text)
        self.assertIn("Two explicit transient user-output exceptions", self.policy("cloud-artifact-transfer"))
        self.assertIn("Never return PUT URLs", self.policy("s3-presigned-file-delivery"))

    def test_hash_verification_and_prompted_cleanup(self):
        text = self.policy("cloud-artifact-transfer")
        for marker in ("bytes/SHA-256 equality", "not ETag", "one fresh signed URL", "one sequential retry", "Only AFTER stored bytes/hash are verified AND the durable reference has been returned", "exact removal prompt", "expected_sha256", "never directories or symlinks"):
            self.assertIn(marker, text)
        with open(os.path.join(CHART, "Chart.yaml"), encoding="utf-8") as handle:
            self.assertEqual(yaml.safe_load(handle)["version"], "0.4.7")


if __name__ == "__main__":
    unittest.main()
