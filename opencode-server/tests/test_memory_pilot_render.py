import glob
import json
import os
import subprocess
import unittest

import yaml

CHART = "opencode-server"
CHART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROD_IMAGE = "ghcr.io/anomalyco/opencode:1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8"
TEI_IMAGE = "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4"
TEI_MODEL = "nomic-ai/nomic-embed-text-v1"
TEI_REVISION = "3ac47f125a41961d13b397d0332866be2f9152e1"
PILOT_FULLNAME = "opencode-memory-pilot"
PILOT_CLAIM = "opencode-memory-pilot-home"
PILOT_ARGS = [
    "--set", "memoryPilot.enabled=true",
    "--set", "fullnameOverride=" + PILOT_FULLNAME,
    "--set", "persistence.existingClaim=" + PILOT_CLAIM,
]
HEALTH_URL = "http://127.0.0.1:8080/health"
HEALTH_CMD = ["curl", "-fsS", HEALTH_URL]


def run_helm(extra):
    return subprocess.run(
        ["helm", "template", "test", CHART] + extra,
        capture_output=True,
        text=True,
    )


def render(extra):
    proc = run_helm(extra)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def render_docs(extra):
    return [doc for doc in yaml.safe_load_all(render(extra)) if doc is not None]


def by_kind(docs, kind):
    matches = [doc for doc in docs if doc["kind"] == kind]
    assert len(matches) == 1, "expected exactly one %s, got %d" % (kind, len(matches))
    return matches[0]


def container(spec, name):
    matches = [item for item in spec["containers"] if item["name"] == name]
    assert len(matches) == 1, "expected exactly one %s container" % name
    return matches[0]


def env_entry(item, name):
    matches = [entry for entry in item["env"] if entry["name"] == name]
    assert matches, "missing env %s" % name
    return matches[0]


def volume(spec, name):
    matches = [item for item in spec["volumes"] if item["name"] == name]
    assert len(matches) == 1, "expected exactly one %s volume" % name
    return matches[0]


def chart_file(*parts):
    with open(os.path.join(CHART_DIR, *parts), "r", encoding="utf-8") as handle:
        return handle.read().rstrip("\n")


def assert_hardened(testcase, item):
    security = item["securityContext"]
    testcase.assertFalse(security["allowPrivilegeEscalation"])
    testcase.assertTrue(security["readOnlyRootFilesystem"])
    testcase.assertEqual(security["capabilities"]["drop"], ["ALL"])


class DefaultRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = render([])
        cls.docs = [doc for doc in yaml.safe_load_all(cls.rendered) if doc is not None]
        cls.config_map = by_kind(cls.docs, "ConfigMap")
        cls.deployment = by_kind(cls.docs, "Deployment")
        cls.spec = cls.deployment["spec"]["template"]["spec"]

    def test_renders_only_production_configmap_and_deployment(self):
        self.assertEqual(sorted(doc["kind"] for doc in self.docs), ["ConfigMap", "Deployment"])
        self.assertEqual(self.config_map["metadata"]["name"], "opencode-config")
        self.assertEqual(self.deployment["metadata"]["name"], "opencode")

    def test_configmap_matches_canonical_chart_files(self):
        data = self.config_map["data"]
        agent_paths = sorted(glob.glob(os.path.join(CHART_DIR, "files", "agents", "*.md")))
        skill_paths = sorted(glob.glob(os.path.join(CHART_DIR, "files", "skills", "*", "SKILL.md")))
        expected_keys = {"opencode.json", "AGENTS.md"}
        self.assertEqual(data["opencode.json"], chart_file("files", "opencode.json"))
        self.assertEqual(data["AGENTS.md"], chart_file("files", "AGENTS.md"))
        for path in agent_paths:
            key = os.path.basename(path)
            expected_keys.add(key)
            self.assertEqual(data[key], chart_file("files", "agents", key), path)
        for path in skill_paths:
            relative = os.path.relpath(path, os.path.join(CHART_DIR, "files"))
            key = relative.replace(os.sep, "-")
            expected_keys.add(key)
            self.assertEqual(data[key], chart_file("files", relative), path)
        self.assertEqual(set(data), expected_keys)

    def test_deployment_keeps_production_behavior(self):
        self.assertNotIn("strategy", self.deployment["spec"])
        self.assertEqual(self.deployment["spec"]["replicas"], 1)
        self.assertEqual([item["name"] for item in self.spec["containers"]], ["opencode"])
        opencode = container(self.spec, "opencode")
        self.assertEqual(opencode["image"], PROD_IMAGE)
        self.assertEqual(opencode["args"], ["web", "--hostname", "0.0.0.0", "--port", "4096"])
        zai = env_entry(opencode, "ZHIPU_API_KEY")["valueFrom"]["secretKeyRef"]
        self.assertEqual(zai, {"name": "opencode-zai", "key": "ZHIPU_API_KEY"})
        mounts = {entry["name"]: entry["mountPath"] for entry in opencode["volumeMounts"]}
        self.assertEqual(mounts["artifacts"], "/artifacts")
        self.assertEqual(
            volume(self.spec, "home"),
            {"name": "home", "persistentVolumeClaim": {"claimName": "opencode-home"}},
        )
        self.assertEqual(
            volume(self.spec, "artifacts"),
            {"name": "artifacts", "persistentVolumeClaim": {"claimName": "opencode-artifacts"}},
        )
        self.assertEqual(
            volume(self.spec, "openai-auth"),
            {"name": "openai-auth", "secret": {"secretName": "opencode-openai-auth"}},
        )

    def test_default_render_carries_no_pilot_surfaces(self):
        for forbidden in ("memory-pilot", "opencode-mem", "text-embeddings-inference"):
            self.assertNotIn(forbidden, self.rendered, forbidden)


class PilotRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = render(PILOT_ARGS)
        cls.docs = [doc for doc in yaml.safe_load_all(cls.rendered) if doc is not None]
        cls.config_map = by_kind(cls.docs, "ConfigMap")
        cls.deployment = by_kind(cls.docs, "Deployment")
        cls.spec = cls.deployment["spec"]["template"]["spec"]

    def test_renders_exactly_pilot_configmap_and_deployment(self):
        self.assertEqual(sorted(doc["kind"] for doc in self.docs), ["ConfigMap", "Deployment"])
        self.assertEqual(self.config_map["metadata"]["name"], PILOT_FULLNAME + "-config")
        self.assertEqual(self.deployment["metadata"]["name"], PILOT_FULLNAME)

    def test_configmap_keys_are_exactly_the_pilot_config(self):
        self.assertEqual(
            sorted(self.config_map["data"]),
            ["AGENTS.md", "opencode-mem.jsonc", "opencode.json"],
        )

    def test_opencode_json_contract(self):
        cfg = json.loads(self.config_map["data"]["opencode.json"])
        self.assertEqual(cfg["$schema"], "https://opencode.ai/config.json")
        self.assertEqual(cfg["model"], "zai-coding-plan/glm-5.3")
        self.assertEqual(cfg["default_agent"], "memory-pilot")
        self.assertEqual(cfg["enabled_providers"], ["zai-coding-plan"])
        self.assertEqual(
            cfg["provider"]["zai-coding-plan"]["options"]["apiKey"],
            "{env:ZHIPU_API_KEY}",
        )
        self.assertEqual(
            cfg["permission"],
            {"*": "deny", "memory": "allow", "StructuredOutput": "allow"},
        )
        for agent in ("build", "plan", "general", "explore"):
            self.assertTrue(cfg["agent"][agent]["disable"], agent)
        pilot = cfg["agent"]["memory-pilot"]
        self.assertEqual(pilot["mode"], "primary")
        self.assertEqual(pilot["permission"], {"*": "deny", "memory": "allow"})
        self.assertIn("synthetic", pilot["prompt"])
        self.assertNotIn("tools", pilot)
        self.assertNotIn("tools", cfg)
        self.assertEqual(cfg["plugin"], ["opencode-mem@2.26.0"])
        self.assertNotIn("mcp", cfg)

    def test_opencode_mem_jsonc_contract(self):
        mem = json.loads(self.config_map["data"]["opencode-mem.jsonc"])
        self.assertEqual(mem["storagePath"], "/home/opencode/.opencode-mem/data")
        self.assertFalse(mem["webServerEnabled"])
        self.assertFalse(mem["autoCleanupEnabled"])
        self.assertTrue(mem["autoCaptureEnabled"])
        self.assertEqual(mem["opencodeProvider"], "zai-coding-plan")
        self.assertEqual(mem["opencodeModel"], "glm-5.3")
        self.assertFalse(mem["injectProfile"])
        self.assertFalse(mem["userProfileAutoCleanupEnabled"])
        self.assertEqual(
            mem["chatMessage"],
            {
                "enabled": True,
                "maxMemories": 3,
                "excludeCurrentSession": True,
                "injectOn": "first",
            },
        )
        self.assertEqual(
            mem["compaction"],
            {"enabled": True, "memoryLimit": 10},
        )
        self.assertEqual(mem["embeddingApiUrl"], "http://127.0.0.1:8080/v1")
        self.assertEqual(mem["embeddingApiKey"], "-")
        self.assertEqual(mem["embeddingModel"], TEI_MODEL)
        self.assertEqual(mem["embeddingDimensions"], 768)
        self.assertTrue(mem["embeddingUseTaskPrefixes"])
        for key in ("memoryProvider", "memoryModel", "memoryApiUrl", "memoryApiKey"):
            self.assertNotIn(key, mem, key)

    def test_agents_md_is_minimal_pilot_instructions(self):
        agents_md = self.config_map["data"]["AGENTS.md"]
        self.assertIn("memory-pilot", agents_md)
        self.assertIn("synthetic", agents_md)
        self.assertIn("not an enforced sandbox", agents_md)

    def test_deployment_is_single_replica_recreate(self):
        self.assertEqual(self.deployment["spec"]["replicas"], 1)
        self.assertEqual(self.deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(
            self.deployment["spec"]["selector"]["matchLabels"],
            {"app": PILOT_FULLNAME},
        )
        template_annotations = self.deployment["spec"]["template"]["metadata"]["annotations"]
        self.assertIn("checksum/opencode-server-config", template_annotations)
        deployment_annotations = self.deployment["metadata"]["annotations"]
        self.assertEqual(
            deployment_annotations["secret.reloader.stakater.com/reload"],
            "opencode-memory-pilot-provider",
        )

    def test_pod_security_context(self):
        self.assertFalse(self.spec["automountServiceAccountToken"])
        security = self.spec["securityContext"]
        self.assertEqual(security["runAsUser"], 1000)
        self.assertEqual(security["runAsGroup"], 1000)
        self.assertEqual(security["fsGroup"], 1000)
        self.assertTrue(security["runAsNonRoot"])
        self.assertEqual(security["seccompProfile"], {"type": "RuntimeDefault"})

    def test_only_config_seeding_init_container(self):
        names = [item["name"] for item in self.spec["initContainers"]]
        self.assertEqual(names, ["seed-opencode-config"])
        self.assertNotIn("auth.json", self.rendered)

    def test_opencode_container(self):
        item = container(self.spec, "opencode")
        self.assertEqual(item["image"], PROD_IMAGE)
        script = item["args"][0]
        self.assertIn(HEALTH_URL, script)
        self.assertIn("-T 2", script)
        self.assertIn("deadline=600", script)
        self.assertIn("$(date +%s)", script)
        self.assertIn("exec /usr/local/bin/opencode web", script)
        self.assertEqual(
            item["startupProbe"],
            {"tcpSocket": {"port": "http"}, "periodSeconds": 10, "failureThreshold": 120},
        )
        provider_key = env_entry(item, "ZHIPU_API_KEY")["valueFrom"]["secretKeyRef"]
        self.assertEqual(
            provider_key,
            {"name": "opencode-memory-pilot-provider", "key": "ZHIPU_API_KEY"},
        )
        server_password = env_entry(item, "OPENCODE_SERVER_PASSWORD")["valueFrom"]["secretKeyRef"]
        self.assertEqual(
            server_password,
            {"name": "opencode-memory-pilot-server-auth", "key": "password"},
        )
        env_names = {entry["name"] for entry in item["env"]}
        self.assertNotIn("KIMI_API_KEY", env_names)
        self.assertNotIn("MINIMAX_API_KEY", env_names)
        self.assertEqual(item["ports"], [{"name": "http", "containerPort": 4096}])
        self.assertEqual(item["readinessProbe"], {"tcpSocket": {"port": "http"}})
        self.assertEqual(item["livenessProbe"], {"tcpSocket": {"port": "http"}})
        mounts = {entry["name"]: entry["mountPath"] for entry in item["volumeMounts"]}
        self.assertEqual(
            mounts,
            {"home": "/home/opencode", "config": "/home/opencode/.config/opencode", "tmp": "/tmp"},
        )

    def test_tei_container(self):
        item = container(self.spec, "tei")
        self.assertEqual(item["image"], TEI_IMAGE)
        self.assertEqual(
            item["args"],
            [
                "--model-id", TEI_MODEL,
                "--revision", TEI_REVISION,
                "--hostname", "127.0.0.1",
                "--port", "8080",
                "--huggingface-hub-cache", "/models",
                "--auto-truncate",
            ],
        )
        self.assertNotIn("ports", item)
        for probe in ("readinessProbe", "livenessProbe", "startupProbe"):
            self.assertEqual(item[probe]["exec"]["command"], HEALTH_CMD, probe)
        self.assertEqual(item["startupProbe"]["periodSeconds"], 10)
        self.assertEqual(item["startupProbe"]["failureThreshold"], 60)
        mounts = {entry["name"]: entry["mountPath"] for entry in item["volumeMounts"]}
        self.assertEqual(mounts, {"models": "/models", "tei-tmp": "/tmp"})

    def test_volumes(self):
        names = {item["name"] for item in self.spec["volumes"]}
        self.assertEqual(
            names, {"home", "config", "config-source", "tmp", "models", "tei-tmp"}
        )
        self.assertEqual(
            volume(self.spec, "home"),
            {"name": "home", "persistentVolumeClaim": {"claimName": PILOT_CLAIM}},
        )
        self.assertEqual(
            volume(self.spec, "config-source"),
            {
                "name": "config-source",
                "configMap": {
                    "name": PILOT_FULLNAME + "-config",
                    "items": [
                        {"key": "opencode.json", "path": "opencode.json"},
                        {"key": "opencode-mem.jsonc", "path": "opencode-mem.jsonc"},
                        {"key": "AGENTS.md", "path": "AGENTS.md"},
                    ],
                },
            },
        )
        for name in ("config", "tmp", "models", "tei-tmp"):
            self.assertEqual(volume(self.spec, name), {"name": name, "emptyDir": {}})
        for item in self.spec["volumes"]:
            self.assertNotIn("secret", item)

    def test_all_containers_hardened(self):
        for item in self.spec["initContainers"] + self.spec["containers"]:
            assert_hardened(self, item)

    def test_no_production_content_in_pilot_render(self):
        for forbidden in (
            "opencode-kimi",
            "opencode-minimax",
            "opencode-openai-auth",
            "opencode-zai",
            "opencode-home",
            "opencode-artifacts",
            "agent-pipe",
            "grillmaster",
            "mcp-apify",
            "artifactsExistingClaim",
        ):
            self.assertNotIn(forbidden, self.rendered, forbidden)


class UnsafePilotValues(unittest.TestCase):
    def assert_render_fails(self, extra, needle):
        proc = run_helm(extra)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(needle, proc.stderr)

    def test_enabled_with_production_defaults_fails(self):
        self.assert_render_fails(["--set", "memoryPilot.enabled=true"], "requires fullnameOverride")

    def test_enabled_with_production_claim_fails(self):
        self.assert_render_fails(
            [
                "--set", "memoryPilot.enabled=true",
                "--set", "fullnameOverride=" + PILOT_FULLNAME,
                "--set", "persistence.existingClaim=opencode-home",
            ],
            "requires persistence.existingClaim",
        )

    def test_enabled_with_empty_claim_fails(self):
        self.assert_render_fails(
            [
                "--set", "memoryPilot.enabled=true",
                "--set", "fullnameOverride=" + PILOT_FULLNAME,
                "--set", "persistence.existingClaim=",
            ],
            "requires persistence.existingClaim",
        )

    def test_enabled_with_near_miss_fullname_fails(self):
        self.assert_render_fails(
            [
                "--set", "memoryPilot.enabled=true",
                "--set", "fullnameOverride=opencode-memory-pilots",
                "--set", "persistence.existingClaim=" + PILOT_CLAIM,
            ],
            "requires fullnameOverride",
        )

    def test_enabled_with_empty_fullname_fails(self):
        self.assert_render_fails(
            [
                "--set", "memoryPilot.enabled=true",
                "--set", "fullnameOverride=",
                "--set", "persistence.existingClaim=" + PILOT_CLAIM,
            ],
            "requires fullnameOverride",
        )

    def test_enabled_with_production_provider_secret_fails(self):
        self.assert_render_fails(
            [
                "--set", "memoryPilot.enabled=true",
                "--set", "fullnameOverride=" + PILOT_FULLNAME,
                "--set", "persistence.existingClaim=" + PILOT_CLAIM,
                "--set", "memoryPilot.providerSecretName=opencode-zai",
            ],
            "requires memoryPilot.providerSecretName",
        )

    def test_enabled_with_production_server_secret_fails(self):
        self.assert_render_fails(
            [
                "--set", "memoryPilot.enabled=true",
                "--set", "fullnameOverride=" + PILOT_FULLNAME,
                "--set", "persistence.existingClaim=" + PILOT_CLAIM,
                "--set", "memoryPilot.serverSecretName=opencode-server-auth",
            ],
            "requires memoryPilot.serverSecretName",
        )


if __name__ == "__main__":
    unittest.main()
