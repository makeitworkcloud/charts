import json
import os
import re
import subprocess
import unittest

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def render(chart):
    result = subprocess.run(
        ["helm", "template", "test", chart], cwd=ROOT,
        capture_output=True, text=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc is not None]


def one(docs, kind):
    matches = [doc for doc in docs if doc["kind"] == kind]
    if len(matches) != 1:
        raise AssertionError("expected one " + kind)
    return matches[0]


class RetainedPresentationRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = render("agent-pipe-uploader")
        cls.deployment = one(cls.docs, "Deployment")
        cls.pod = cls.deployment["spec"]["template"]["spec"]
        cls.profiles = json.loads(one(cls.docs, "ConfigMap")["data"]["profiles.json"])["profiles"]
        cls.config = json.loads(one(render("opencode-server"), "ConfigMap")["data"]["opencode.json"])

    def test_exact_profiles_operations_hosts_and_prefixes(self):
        expected = {
            "agent-pipe": (["upload", "download", "verify"], ["agent-pipe.s3.amazonaws.com", "agent-pipe.s3.us-west-2.amazonaws.com"], ["/deliveries/"]),
            "agent-presentations": (["upload", "download", "verify"], ["agent-pipe.s3.amazonaws.com", "agent-pipe.s3.us-west-2.amazonaws.com"], ["/presentations/"]),
            "slidespeak-exports": (["download", "verify"], ["slidespeak-files.s3.amazonaws.com", "slidespeak-files.s3.us-east-2.amazonaws.com"], ["/"]),
        }
        self.assertEqual(set(self.profiles), set(expected))
        for name, (operations, hosts, prefixes) in expected.items():
            self.assertEqual(self.profiles[name], {
                "operations": operations,
                "allowedHosts": hosts,
                "pathPrefixes": prefixes,
                "requiredQueryParameters": ["X-Amz-Algorithm", "X-Amz-Credential", "X-Amz-Date", "X-Amz-Expires", "X-Amz-SignedHeaders", "X-Amz-Signature"],
                "maxBytes": 104857600,
            }, name)

    def test_no_home_credentials_or_service_account_and_recreate(self):
        self.assertEqual(sorted(doc["kind"] for doc in self.docs), ["ConfigMap", "Deployment", "Service"])
        self.assertEqual(self.deployment["spec"]["replicas"], 1)
        self.assertEqual(self.deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(self.deployment["spec"]["selector"]["matchLabels"], {"app": "agent-pipe-uploader"})
        self.assertFalse(self.pod["automountServiceAccountToken"])
        self.assertNotIn("initContainers", self.pod)
        self.assertEqual(self.pod["volumes"], [
            {"name": "artifacts", "persistentVolumeClaim": {"claimName": "opencode-artifacts"}},
            {"name": "profiles", "configMap": {"name": "agent-pipe-uploader-config"}},
            {"name": "tmp", "emptyDir": {}},
        ])
        self.assertEqual(len(self.pod["containers"]), 1)
        helper = self.pod["containers"][0]
        self.assertEqual(helper["volumeMounts"], [
            {"name": "artifacts", "mountPath": "/artifacts"},
            {"name": "profiles", "mountPath": "/etc/agent-pipe", "readOnly": True},
            {"name": "tmp", "mountPath": "/tmp"},
        ])
        self.assertEqual({item["name"] for item in helper["env"]}, {"MCP_ALLOWED_HOSTS", "PROFILE_CONFIG_PATH", "HOME", "PYTHONDONTWRITEBYTECODE"})
        self.assertTrue(all("value" in item and "valueFrom" not in item for item in helper["env"]))
        self.assertNotIn("envFrom", helper)
        self.assertTrue(helper["securityContext"]["readOnlyRootFilesystem"])
        self.assertFalse(helper["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(helper["securityContext"]["capabilities"]["drop"], ["ALL"])

    def test_pin_shape_not_publication_evidence(self):
        image = self.pod["containers"][0]["image"]
        self.assertRegex(image, r"^ghcr\.io/makeitworkcloud/agent-pipe-uploader:[0-9a-f]{40}(@sha256:[0-9a-f]{64})?$")
        self.assertNotIn(":latest", image)
        annotations = self.deployment["spec"]["template"]["metadata"]["annotations"]
        self.assertRegex(annotations["checksum/agent-pipe-uploader-config"], r"^[0-9a-f]{64}$")
        with open(os.path.join(ROOT, "agent-pipe-uploader", "values.yaml"), encoding="utf-8") as handle:
            values = handle.read()
        if "63ccfde32e70decf81255e816cd2ada57b4f7e10" in image:
            self.assertIn("STAGING ONLY", values)
            self.assertIn("MERGE BLOCKER", values)

    def test_exact_permission_inventory(self):
        permissions = {name: {"/artifacts/*": "allow", "/repos/*": "allow"} for name in ("external_directory", "glob", "grep", "list", "read", "edit")}
        permissions.update({
            "agent-pipe_download_artifact": "ask",
            "agent-pipe_inspect_artifact": "allow",
            "agent-pipe_remove_artifact": "ask",
            "agent-pipe_upload_artifact": "ask",
            "agent-pipe_verify_download": "allow",
        })
        self.assertEqual(self.config["permission"], permissions)
        self.assertEqual(self.config["mcp"]["agent-pipe"], {"type": "remote", "url": "http://agent-pipe-uploader.opencode.svc:8080/mcp", "enabled": True, "oauth": False})

    def test_chart_versions_and_existing_test_wiring(self):
        for chart, version in (("agent-pipe-uploader", "0.3.0"), ("opencode-server", "0.4.7")):
            with open(os.path.join(ROOT, chart, "Chart.yaml"), encoding="utf-8") as handle:
                self.assertEqual(yaml.safe_load(handle)["version"], version)
        with open(os.path.join(ROOT, "Makefile"), encoding="utf-8") as handle:
            makefile = handle.read()
        test = makefile.split("\ntest:\n", 1)[1].split("\ntest-changed-charts:\n", 1)[0]
        self.assertIn("$(MAKE) test-retained-presentations", test)
        self.assertIn("python3 agent-pipe-uploader/tests/test_retained_presentation_render.py", makefile)


if __name__ == "__main__":
    unittest.main()
