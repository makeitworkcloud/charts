import json
import os
import subprocess
import unittest

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class UploaderRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["helm", "template", "test", "agent-pipe-uploader"], cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc is not None]
        cls.deployment = next(doc for doc in cls.docs if doc["kind"] == "Deployment")
        cls.pod = cls.deployment["spec"]["template"]["spec"]
        config = next(doc for doc in cls.docs if doc["kind"] == "ConfigMap")
        cls.profiles = json.loads(config["data"]["profiles.json"])["profiles"]

    def test_exact_profiles(self):
        expected = {
            "agent-pipe": (["upload", "download", "verify"], ["agent-pipe.s3.amazonaws.com", "agent-pipe.s3.us-west-2.amazonaws.com"], ["/deliveries/"]),
            "agent-presentations": (["upload", "download", "verify"], ["agent-pipe.s3.amazonaws.com", "agent-pipe.s3.us-west-2.amazonaws.com"], ["/presentations/"]),
            "slidespeak-exports": (["download", "verify"], ["slidespeak-files.s3.amazonaws.com", "slidespeak-files.s3.us-east-2.amazonaws.com"], ["/"]),
        }
        self.assertEqual(set(self.profiles), set(expected))
        for name, (operations, hosts, prefixes) in expected.items():
            self.assertEqual(self.profiles[name], {
                "operations": operations, "allowedHosts": hosts, "pathPrefixes": prefixes,
                "requiredQueryParameters": ["X-Amz-Algorithm", "X-Amz-Credential", "X-Amz-Date", "X-Amz-Expires", "X-Amz-SignedHeaders", "X-Amz-Signature"],
                "maxBytes": 104857600,
            }, name)

    def test_isolated_mounts_security_and_recreate(self):
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

    def test_own_version(self):
        with open(os.path.join(ROOT, "agent-pipe-uploader", "Chart.yaml"), encoding="utf-8") as handle:
            self.assertEqual(yaml.safe_load(handle)["version"], "0.3.0")


if __name__ == "__main__":
    unittest.main()
