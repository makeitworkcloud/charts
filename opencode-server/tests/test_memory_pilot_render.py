import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import yaml

CHART = "opencode-server"
CHART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REPO_ROOT = os.path.abspath(os.path.join(CHART_DIR, ".."))
BASELINE_SHA = "32a6b91cc3a881b861bdac087655c3935bb15454"
PRIMARY_POLICY_BASELINE_SHA = "2f5d497c72763d38fe9e7cfdabab1eabec6264a9"
PROD_IMAGE = "ghcr.io/anomalyco/opencode:2.0.22@sha256:11f2b6c96d380867387fbee390c06cb47efffd9fdc37009b4cd40795b45dad19"
# The opt-in memory pilot stays on the historical v1 image independently of
# the production pin.
PILOT_IMAGE = "ghcr.io/anomalyco/opencode:1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8"
# Approved production runtime changes applied to the extracted historical
# baseline before parity rendering. Each transform asserts the exact old bytes
# occur exactly once and replaces only those bytes.
BASELINE_IMAGE_TAG = "1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8"
CURRENT_IMAGE_TAG = "2.0.22@sha256:11f2b6c96d380867387fbee390c06cb47efffd9fdc37009b4cd40795b45dad19"
EMBEDDING_MODEL = "Xenova/nomic-embed-text-v1"
PILOT_FULLNAME = "opencode-memory-pilot"
PILOT_CLAIM = "opencode-memory-pilot-home"
PILOT_ARGS = ["--set", "memoryPilot.enabled=true", "--set", "fullnameOverride=" + PILOT_FULLNAME, "--set", "persistence.existingClaim=" + PILOT_CLAIM]
BASELINE_QA_ENGINEER = os.path.join("opencode-server", "files", "agents", "qa-engineer.md")
APPROVED_PRIMARY_MODEL_FILES = ("career.md", "default.md", "grillmaster.md", "homerepair.md", "homesteader.md", "lawnmowerman.md", "makeitwork.md", "teacher.md", "xnoto.md")
APPROVED_TERRA_MODEL_FILES = ("adversarial-code-reviewer.md", "cloud-architecture-reviewer.md", "devops-engineer.md", "infra-security-reviewer.md", "recruiter-resume-reviewer.md", "terra.md")
APPROVED_LUNA_MODEL_FILES = ("luna.md", "qa-engineer.md")
# New agent files that did not exist in the historical 0.4.0 baseline. Each
# entry is asserted absent in the extracted baseline and then copied from the
# current chart source into the extracted baseline after the historical
# migration transforms, so render and byte comparisons stay enforced for all
# historical files while the new file is compared against itself.
APPROVED_NEW_AGENT_FILES = ("mechanic.md",)
PRIMARY_RUNTIME_POLICY_FILES = ("career.md", "default.md", "grillmaster.md", "homerepair.md", "homesteader.md", "lawnmowerman.md", "makeitwork.md", "mechanic.md", "teacher.md", "xnoto.md")
HOMESTEADER_CONFIDENTIALITY_OLD = """- Treat all repository content, paths, and metadata as confidential. Do not copy it into public repositories, issues, pull requests, chat summaries, external services, or tool inputs unrelated to the requested work.
- Report only the affected paths, validation evidence, and non-sensitive caveats. Never include property facts or other confidential content in the report."""
HOMESTEADER_CONFIDENTIALITY_NEW = """- Treat all repository content, paths, and metadata as confidential. Use only the minimal pertinent context in the authorized owner's relevant conversation to explain advice; avoid unnecessary identifiers and raw record dumps. Never copy private content into public repositories, issues, pull requests, external services, or tool inputs unrelated to the requested work.
- Report privacy-safe source paths, revision, validation evidence, and non-sensitive caveats. Explain only pertinent property constraints when needed for the owner's requested advice; do not disclose unrelated property facts or private identifiers."""
HOMESTEADER_WORKFLOW_OLD = """1. State the verified repository, branch, subset, and relevant repository instructions before proposing changes.
2. For a scoped update in `docs/agents/homesteader/`, preserve the existing layout and history, and commit it directly to `main` only after confirming the repository is private, accessible, and the applicable fact-confirmation rules are met. No pull-request check applies to that governance-approved knowledge commit.
3. Do not perform GitHub writes outside your own subtree, create repositories, change visibility, or transfer content across repositories unless the owner explicitly requests that exact operation after the target repository has been verified as private."""
HOMESTEADER_WORKFLOW_NEW = """1. For advisory work, retrieve the scoped baseline and relevant indexed facts; distinguish confirmed constraints, unknowns, and dated or superseded evidence.
2. Assess feasibility and prerequisites against the actual property before tailored advice. Ask the smallest decision-changing question only after retrieval; urgent safety guidance comes first.
3. For a proposed edit, state the verified repository, branch, subset, and relevant repository instructions before changes. Advice alone is not authorization to edit.
4. For a scoped update in `docs/agents/homesteader/`, preserve the existing layout and history, and commit it directly to `main` only after confirming the repository is private, accessible, and the applicable fact-confirmation rules are met. No pull-request check applies to that governance-approved knowledge commit.
5. Do not perform GitHub writes outside your own subtree, create repositories, change visibility, or transfer content across repositories unless the owner explicitly requests that exact operation after the target repository has been verified as private."""
APPROVED_KIMI_PROVIDER_MODEL_SUFFIXES = {"kimi.md": b"k3", "kimi-256k.md": b"k3-256k", "docs-writer.md": b"k3-256k", "release-engineer.md": b"k3-256k"}
APPROVED_KIMI_PROVIDER_CONFIG_LINES = (
    (b'"model": "kimi-for-coding/k3",', b'"model": "kimi-code-plan-cn/k3",'),
    (b'"enabled_providers": ["kimi-for-coding",', b'"enabled_providers": ["kimi-code-plan-cn",'),
    (b'"provider": {"kimi-for-coding": {"options": {"apiKey": "{env:KIMI_API_KEY}"}}},', b'"provider": {"kimi-code-plan-cn": {"options": {"apiKey": "{env:KIMI_API_KEY}"}}},'),
)


def run_helm(extra):
    return subprocess.run(["helm", "template", "test", CHART] + extra, capture_output=True, text=True)


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


class BaselineParity(unittest.TestCase):
    def _replace_frontmatter_line(self, agents_dir, name, old, new):
        path = os.path.join(agents_dir, name)
        with open(path, "rb") as handle:
            content = handle.read()
        parts = content.split(b"---\n", 2)
        self.assertEqual(len(parts), 3, name)
        self.assertEqual(parts[0], b"", name)
        self.assertEqual(parts[1].count(old), 1, name)
        parts[1] = parts[1].replace(old, new)
        with open(path, "wb") as handle:
            handle.write(b"---\n".join(parts))

    def _apply_approved_model_changes(self, baseline_chart):
        agents_dir = os.path.join(baseline_chart, "files", "agents")
        primary_old = b"mode: primary\nmodel: openai/gpt-5.6-terra\nvariant: default\n"
        primary_new = b"mode: primary\nmodel: openai/gpt-6.1-sol\n"
        for name in APPROVED_PRIMARY_MODEL_FILES:
            self._replace_frontmatter_line(agents_dir, name, primary_old, primary_new)
        for name in APPROVED_TERRA_MODEL_FILES:
            self._replace_frontmatter_line(agents_dir, name, b"model: openai/gpt-5.6-terra\n", b"model: openai/gpt-6-sol\n")
        for name in APPROVED_LUNA_MODEL_FILES:
            self._replace_frontmatter_line(agents_dir, name, b"model: openai/gpt-5.6-luna\n", b"model: openai/gpt-6-luna\n")

    def _apply_approved_homesteader_changes(self, baseline_chart):
        path = os.path.join(baseline_chart, "files", "agents", "homesteader.md")
        with open(path, "rb") as handle:
            content = handle.read()
        for old, new in ((HOMESTEADER_CONFIDENTIALITY_OLD, HOMESTEADER_CONFIDENTIALITY_NEW), (HOMESTEADER_WORKFLOW_OLD, HOMESTEADER_WORKFLOW_NEW)):
            before = old.encode("utf-8")
            self.assertEqual(content.count(before), 1, old)
            content = content.replace(before, new.encode("utf-8"))
        with open(path, "wb") as handle:
            handle.write(content)

    def _apply_primary_runtime_policy(self, baseline_chart):
        baseline_agents = os.path.join(baseline_chart, "files", "agents")
        current_agents = os.path.join(CHART_DIR, "files", "agents")
        self.assertEqual(len(PRIMARY_RUNTIME_POLICY_FILES), 10)
        for name in PRIMARY_RUNTIME_POLICY_FILES:
            target = os.path.join(baseline_agents, name)
            self.assertTrue(os.path.isfile(target), name)
            with open(os.path.join(current_agents, name), "rb") as handle:
                content = handle.read()
            with open(target, "wb") as handle:
                handle.write(content)

        floor_path = os.path.join(baseline_chart, "files", "AGENTS.md")
        with open(floor_path, "rb") as handle:
            old_floor = handle.read()
        with open(os.path.join(CHART_DIR, "files", "AGENTS.md"), "rb") as handle:
            new_floor = handle.read()
        old_marker = b"## Common repository routing\n"
        new_marker = b"## Subagent repository routing\n"
        self.assertEqual(old_floor.count(old_marker), 1)
        self.assertEqual(new_floor.count(new_marker), 1)
        self.assertEqual(old_floor.split(old_marker, 1)[0], new_floor.split(new_marker, 1)[0])
        with open(floor_path, "wb") as handle:
            handle.write(new_floor)

    def _apply_approved_provider_migration(self, baseline_chart):
        agents_dir = os.path.join(baseline_chart, "files", "agents")
        for name, model_suffix in APPROVED_KIMI_PROVIDER_MODEL_SUFFIXES.items():
            self._replace_frontmatter_line(agents_dir, name, b"model: kimi-for-coding/" + model_suffix + b"\n", b"model: kimi-code-plan-cn/" + model_suffix + b"\n")
        config_path = os.path.join(baseline_chart, "files", "opencode.json")
        with open(config_path, "rb") as handle:
            content = handle.read()
        for old_line, new_line in APPROVED_KIMI_PROVIDER_CONFIG_LINES:
            self.assertEqual(content.count(old_line), 1, old_line.decode("ascii"))
            content = content.replace(old_line, new_line)
        with open(config_path, "wb") as handle:
            handle.write(content)

    def _apply_approved_new_agent_files(self, baseline_chart):
        baseline_agents = os.path.join(baseline_chart, "files", "agents")
        current_agents = os.path.join(CHART_DIR, "files", "agents")
        for name in APPROVED_NEW_AGENT_FILES:
            baseline_path = os.path.join(baseline_agents, name)
            self.assertFalse(os.path.exists(baseline_path), name)
            with open(os.path.join(current_agents, name), "rb") as handle:
                content = handle.read()
            with open(baseline_path, "wb") as handle:
                handle.write(content)

    def _apply_approved_production_runtime_changes(self, baseline_chart):
        values_path = os.path.join(baseline_chart, "values.yaml")
        with open(values_path, "rb") as handle:
            content = handle.read()
        old_tag = BASELINE_IMAGE_TAG.encode("utf-8")
        new_tag = CURRENT_IMAGE_TAG.encode("utf-8")
        self.assertEqual(content.count(old_tag), 1)
        content = content.replace(old_tag, new_tag)
        with open(values_path, "wb") as handle:
            handle.write(content)
        deployment_path = os.path.join(baseline_chart, "templates", "deployment.yaml")
        with open(deployment_path, "rb") as handle:
            content = handle.read()
        for old, new in (
            (b"args: [web, --hostname, 0.0.0.0, --port, \"4096\"]", b"args: [serve, --hostname, 0.0.0.0, --port, \"4096\"]"),
            (b"spec:\n  replicas: 1\n  selector:\n", b"spec:\n  replicas: 1\n  strategy:\n    type: Recreate\n  selector:\n"),
            (b"            - name: MINIMAX_API_KEY\n              valueFrom:\n                secretKeyRef: {name: {{ .Values.secrets.minimax }}, key: MINIMAX_API_KEY}\n            - name: OPENCODE_SERVER_PASSWORD\n", b"            - name: MINIMAX_API_KEY\n              valueFrom:\n                secretKeyRef: {name: {{ .Values.secrets.minimax }}, key: MINIMAX_API_KEY}\n            - name: OPENCODE_DB\n              value: opencode.db\n            - name: OPENCODE_SERVER_PASSWORD\n"),
        ):
            self.assertEqual(content.count(old), 1)
            content = content.replace(old, new)
        with open(deployment_path, "wb") as handle:
            handle.write(content)
        configmap_path = os.path.join(baseline_chart, "templates", "configmap.yaml")
        with open(configmap_path, "rb") as handle:
            content = handle.read()
        old = b'  name: {{ include "opencode-server.fullname" . }}-config\ndata:\n'
        new = b'  name: {{ include "opencode-server.fullname" . }}-config\n  annotations:\n    argocd.argoproj.io/sync-options: ServerSideApply=true\ndata:\n'
        self.assertEqual(content.count(old), 1)
        content = content.replace(old, new)
        with open(configmap_path, "wb") as handle:
            handle.write(content)

    def _extract_baseline(self, tmp):
        archive = subprocess.run(["git", "archive", "--format=tar", BASELINE_SHA, "opencode-server"], capture_output=True, cwd=REPO_ROOT)
        self.assertEqual(archive.returncode, 0, archive.stderr.decode("utf-8", "replace"))
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp, filter="data")
        baseline_chart = os.path.join(tmp, "opencode-server")
        self._apply_approved_model_changes(baseline_chart)
        self._apply_approved_homesteader_changes(baseline_chart)
        self._apply_approved_provider_migration(baseline_chart)
        self._apply_approved_new_agent_files(baseline_chart)
        self._apply_primary_runtime_policy(baseline_chart)
        self._apply_approved_production_runtime_changes(baseline_chart)
        return baseline_chart

    def _render_chart(self, chart_path):
        proc = subprocess.run(["helm", "template", "test", chart_path], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [doc for doc in yaml.safe_load_all(proc.stdout) if doc is not None]

    def _raw_configmap_include(self, chart_path):
        probe_root = tempfile.mkdtemp(prefix="opencode-server-probe-")
        try:
            probe_chart = os.path.join(probe_root, "probe")
            shutil.copytree(chart_path, probe_chart)
            with open(os.path.join(probe_chart, "templates", "zz-raw-probe.yaml"), "w", encoding="utf-8") as handle:
                handle.write('probe: {{ include (print $.Template.BasePath "/configmap.yaml") . | toJson }}\n')
            proc = subprocess.run(["helm", "template", "test", probe_chart], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for doc in yaml.safe_load_all(proc.stdout):
                if isinstance(doc, dict) and "probe" in doc:
                    return doc["probe"]
            self.fail("probe document not found for %s" % chart_path)
        finally:
            shutil.rmtree(probe_root)

    def test_production_render_matches_baseline_with_approved_agent_changes(self):
        with tempfile.TemporaryDirectory(prefix="opencode-server-baseline-") as tmp:
            baseline_chart = self._extract_baseline(tmp)
            qa_engineer = os.path.join(tmp, BASELINE_QA_ENGINEER)
            with open(qa_engineer, "rb") as handle:
                pristine = handle.read()
            self.assertFalse(pristine.endswith(b"\n"))
            with open(qa_engineer, "wb") as handle:
                handle.write(pristine + b"\n")
            baseline_docs = self._render_chart(baseline_chart)
            current_docs = [doc for doc in yaml.safe_load_all(render([])) if doc is not None]
            try:
                self.assertEqual(current_docs, baseline_docs)
            except AssertionError:
                current_raw = self._raw_configmap_include(CHART_DIR)
                baseline_raw = self._raw_configmap_include(baseline_chart)
                print("current include sha256:", hashlib.sha256(current_raw.encode("utf-8")).hexdigest())
                print("baseline include sha256:", hashlib.sha256(baseline_raw.encode("utf-8")).hexdigest())
                print("current include prefix:", json.dumps(current_raw[:50]))
                print("current include suffix:", json.dumps(current_raw[-50:]))
                print("baseline include prefix:", json.dumps(baseline_raw[:50]))
                print("baseline include suffix:", json.dumps(baseline_raw[-50:]))
                raise

    def test_baseline_configmap_semantics_match_current(self):
        with tempfile.TemporaryDirectory(prefix="opencode-server-baseline-") as tmp:
            baseline_chart = self._extract_baseline(tmp)
            baseline_config = by_kind(self._render_chart(baseline_chart), "ConfigMap")
            current_config = by_kind(render_docs([]), "ConfigMap")
            self.assertEqual(current_config["data"], baseline_config["data"])

    def test_approved_agent_runtime_changes_are_exact_and_rendered(self):
        with tempfile.TemporaryDirectory(prefix="opencode-server-baseline-") as tmp:
            baseline_chart = self._extract_baseline(tmp)
            baseline_agents = os.path.join(baseline_chart, "files", "agents")
            current_agents = os.path.join(CHART_DIR, "files", "agents")
            self.assertEqual(sorted(os.listdir(current_agents)), sorted(os.listdir(baseline_agents)))
            self.assertEqual(len(PRIMARY_RUNTIME_POLICY_FILES), 10)
            expected = {"career.md", "default.md", "grillmaster.md", "homerepair.md", "homesteader.md", "lawnmowerman.md", "makeitwork.md", "mechanic.md", "teacher.md", "xnoto.md"}
            self.assertEqual(set(PRIMARY_RUNTIME_POLICY_FILES), expected)
            for name in sorted(os.listdir(current_agents)):
                with open(os.path.join(baseline_agents, name), "rb") as handle:
                    baseline_bytes = handle.read()
                with open(os.path.join(current_agents, name), "rb") as handle:
                    current_bytes = handle.read()
                if name in PRIMARY_RUNTIME_POLICY_FILES:
                    continue
                if name == "qa-engineer.md":
                    self.assertEqual(current_bytes, baseline_bytes + b"\n")
                else:
                    self.assertEqual(current_bytes, baseline_bytes, name)

    def test_approved_new_agent_file_set_is_exactly_mechanic(self):
        self.assertEqual(APPROVED_NEW_AGENT_FILES, ("mechanic.md",))


class PrimaryModelContract(unittest.TestCase):
    def test_exactly_ten_primary_headers_use_gpt_6_1_sol_without_variant(self):
        expected = {"default.md", "makeitwork.md", "xnoto.md", "career.md", "teacher.md", "grillmaster.md", "homerepair.md", "homesteader.md", "lawnmowerman.md", "mechanic.md"}
        actual = set()
        for path in sorted(glob.glob(os.path.join(CHART_DIR, "files", "agents", "*.md"))):
            name = os.path.basename(path)
            with open(path, "r", encoding="utf-8") as handle:
                parts = handle.read().split("---\n", 2)
            self.assertEqual(len(parts), 3, name)
            self.assertEqual(parts[0], "", name)
            header = yaml.safe_load(parts[1])
            self.assertIsInstance(header, dict, name)
            if header.get("mode") == "primary":
                actual.add(name)
            if name in expected or header.get("mode") == "primary":
                with self.subTest(agent=name):
                    self.assertEqual(header.get("mode"), "primary")
                    self.assertEqual(header.get("model"), "openai/gpt-6.1-sol")
                    self.assertNotIn("variant", header)
                    keys = [key.value for key, value in yaml.compose(parts[1]).value]
                    self.assertEqual(len(keys), len(set(keys)), "duplicate frontmatter key")
        self.assertEqual(actual, expected)


class PersistentKnowledgePolicyContract(unittest.TestCase):
    def test_all_primary_agents_have_early_identical_runtime_protocol_and_scope(self):
        agents_dir = os.path.join(CHART_DIR, "files", "agents")
        protocols = []
        primary_names = set(PRIMARY_RUNTIME_POLICY_FILES)
        self.assertEqual(len(primary_names), 10)
        for name in sorted(os.listdir(agents_dir)):
            with open(os.path.join(agents_dir, name), "r", encoding="utf-8") as handle:
                text = handle.read()
            if name not in primary_names:
                self.assertNotIn("## Persistent knowledge protocol", text, name)
                self.assertNotIn("## Knowledge scope", text, name)
                continue
            self.assertEqual(text.count("## Persistent knowledge protocol"), 1, name)
            self.assertEqual(text.count("## Knowledge scope"), 1, name)
            self.assertLess(text.index("## Persistent knowledge protocol"), text.index("## Knowledge scope"), name)
            self.assertLess(text.index("## Knowledge scope"), text.index("## Primary operating rules"), name)
            block = text.split("## Persistent knowledge protocol\n\n", 1)[1].split("\n\n## Knowledge scope", 1)[0]
            protocols.append(block)
            for marker in ("unconditional part of every session", "Before the first substantive task in a new session", "Before planning, external research, advice, diagnosis or edits for each new substantive task or subject", "all five curation gates", "Do not create one document or dated entry per task", "Read permission does not confer write authority", "Never retrieve or store secrets"):
                self.assertIn(marker.lower(), block.lower(), (name, marker))
            scope = text.split("## Knowledge scope\n", 1)[1].split("\n\n## Repository source retrieval", 1)[0].split("\n\n## Cache root aliases", 1)[0]
            if name == "default.md":
                for marker in ("AGENTS.md", "README.md", "docs/README.md", "docs/agents/README.md", "no autonomous write scope", "no other agent's private records"):
                    self.assertIn(marker.lower(), scope.lower(), (name, marker))
            else:
                for marker in ("scope/authority/source-constraints records", "all mandatory entry records", "minimum current core", "disclose that gap", "do not scan the whole subtree"):
                    self.assertIn(marker.lower(), scope.lower(), (name, marker))
        self.assertEqual(len(protocols), 10)
        self.assertEqual(len(set(protocols)), 1, "common runtime protocol must be byte-identical")

    def test_primary_retrieval_is_identical_and_bootstrap_is_not_worker_duty(self):
        blocks = []
        for name in sorted(PRIMARY_RUNTIME_POLICY_FILES):
            with open(os.path.join(CHART_DIR, "files", "agents", name), "r", encoding="utf-8") as handle:
                text = handle.read()
            marker = "## Repository source retrieval\n\n"
            self.assertEqual(text.count(marker), 1, name)
            block = text.split(marker, 1)[1].split("\n\n## Primary operating rules", 1)[0]
            blocks.append(block)
            for phrase in ("actively bootstrap", "reader manifest", "shared PVC", "not a standing reason", "resume codebase-memory", "Reuse unchanged mapping", "source_clipped", "verified snapshot"):
                self.assertIn(phrase, block, (name, phrase))
        self.assertEqual(len(set(blocks)), 1)
        with open(os.path.join(CHART_DIR, "files", "AGENTS.md"), "r", encoding="utf-8") as handle:
            floor = handle.read()
        self.assertIn("## Subagent repository routing", floor)
        self.assertIn("report it to the parent", floor)
        self.assertIn("or bootstrap writer mappings", floor)
        self.assertNotIn("actively bootstrap", floor)
        self.assertLess(len(floor.split("## Subagent repository routing", 1)[1].split()), 400)

    def test_primary_operating_rules_and_role_contracts_match_pinned_base(self):
        marker = b"## Primary operating rules\n"
        for name in sorted(PRIMARY_RUNTIME_POLICY_FILES):
            relative = os.path.join("opencode-server", "files", "agents", name)
            result = subprocess.run(["git", "show", "%s:%s" % (PRIMARY_POLICY_BASELINE_SHA, relative)], capture_output=True, cwd=REPO_ROOT)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            with open(os.path.join(CHART_DIR, "files", "agents", name), "rb") as handle:
                current = handle.read()
            baseline = result.stdout
            self.assertEqual(current.count(marker), 1, name)
            self.assertEqual(baseline.count(marker), 1, name)
            expected = baseline[baseline.index(marker):]
            prefixes = (
                b"- Before the first GitHub search or write",
                b"- For repository discovery and content exploration",
                b"- Documentation sources and knowledge bases require",
                b"- Trust cache provenance only through the verified writer mapping",
                b"- For cached source reads",
                b"- On fallback, log the specific failed check",
            )
            for prefix in prefixes:
                pattern = rb"(?m)^" + re.escape(prefix) + rb"[^\n]*(?:\n  [^\n]*)*\n?"
                expected, count = re.subn(pattern, b"", expected)
                self.assertEqual(count, 1, (name, prefix))
            self.assertEqual(current[current.index(marker):], expected, name)

    def test_role_specific_prerequisites_are_preserved(self):
        markers = {
            "career.md": ("confirmed background, goals, constraints", "never invent qualifications"),
            "teacher.md": ("audience, objectives, source restrictions, delivery needs",),
            "grillmaster.md": ("equipment and preferences", "sources and research", "technique-default records", "source hierarchy"),
            "homerepair.md": ("assets.md", "jobs/README.md", "before diagnosis"),
            "homesteader.md": ("workspace/AGENTS.md", "workspace/property.md", "site, climate, water", "feasibility and prerequisites"),
            "lawnmowerman.md": ("actual machine and engine", "service history", "manufacturer"),
            "mechanic.md": ("actual vehicle (year, market, build date", "service history", "manufacturer documentation"),
            "makeitwork.md": ("advisory planning", "decisions, exceptions, ownership", "canonical repository"),
            "xnoto.md": ("advisory planning", "decisions, exceptions, ownership", "canonical repository"),
        }
        for name, phrases in markers.items():
            with open(os.path.join(CHART_DIR, "files", "agents", name), "r", encoding="utf-8") as handle:
                text = handle.read().lower()
            for phrase in phrases:
                self.assertIn(phrase.lower(), text, (name, phrase))

    def test_default_shared_baseline_is_explicit_and_bounded(self):
        with open(os.path.join(CHART_DIR, "files", "agents", "default.md"), "r", encoding="utf-8") as handle:
            text = handle.read().lower()
        self.assertNotIn("## owner-context routing", text)
        self.assertIn("## knowledge scope\n", text)
        self.assertIn("## primary operating rules\n", text)
        scope = text.split("## knowledge scope\n", 1)[1].split("\n\n## primary operating rules", 1)[0]
        baseline = "the kb-root (`makeitworkcloud/agent-knowledge`) baseline is exactly `agents.md`, `readme.md`, `docs/readme.md`, and `docs/agents/readme.md` (governance only)."
        self.assertIn(baseline, scope)
        for marker in ("no assigned", "no autonomous write scope", "disclose that gap", "load only this minimum baseline", "read no other agent's private records", "do not scan private homes"):
            self.assertIn(marker, scope)

        decoy = "unrelated prompt text\n" + baseline + "\n\n## knowledge scope\n- no designation\n\n## primary operating rules\n"
        decoy_scope = decoy.split("## knowledge scope\n", 1)[1].split("\n\n## primary operating rules", 1)[0]
        self.assertIn(baseline, decoy)
        self.assertNotIn(baseline, decoy_scope)

    def test_docs_describe_runtime_contract_and_new_primary_onboarding(self):
        texts = []
        for relative in (os.path.join("docs", "agent-instruction-architecture.md"), "README.md"):
            with open(os.path.join(CHART_DIR, relative), "r", encoding="utf-8") as handle:
                text = " ".join(handle.read().split()).lower()
            texts.append(text)
            self.assertIn("new primary", text, relative)
            self.assertIn("separately seeded", text, relative)
        combined = " ".join(texts)
        self.assertIn("unconditionally loads", combined)
        self.assertIn("public static ci cannot verify private seed facts", combined)
        self.assertIn("not proof that retrieval behavior has been tested", combined)
class MechanicAgentContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(CHART_DIR, "files", "agents", "mechanic.md")
        with open(path, "r", encoding="utf-8") as handle:
            cls.content = handle.read()
        cls.policy = " ".join(cls.content.split()).lower()

    def test_frontmatter_is_gpt_6_1_sol_primary_without_variant(self):
        parts = self.content.split("---\n", 2)
        self.assertEqual(len(parts), 3)
        header = parts[1]
        self.assertIn("description: ", header)
        self.assertEqual(header.count("mode: primary\n"), 1)
        self.assertEqual(header.count("model: openai/gpt-6.1-sol\n"), 1)
        self.assertNotIn("variant:", header)

    def test_knowledge_home_namespace_and_layout(self):
        self.assertIn("docs/agents/mechanic/", self.content)
        self.assertNotIn("docs/agents/lawnmowerman/", self.content)
        for marker in (
            "vehicles.md",
            "vehicles/<stable-nickname>.md",
            "procedures/<vehicle-id>/<task>.md",
            "templates/vehicle.md",
            "templates/procedure.md",
        ):
            self.assertIn(marker, self.content, marker)

    def test_automotive_safety_privacy_documentation_markers(self):
        for marker in (
            "stop driving",
            "tow",
            "brake",
            "steering",
            "fuel leak",
            "overheating",
            "oil-pressure",
            "roadworthy",
            "owner confirms",
            "vin",
            "recall",
            "freeze-frame",
            "jack stands",
            "high-voltage",
            "airbag",
            "pretensioner",
            "adas",
            "refrigerant",
            "torque",
            "redact",
            "observed",
            "suspected",
            "oem",
            "applicability",
        ):
            self.assertIn(marker, self.policy, marker)

    def test_production_configmap_mounts_mechanic(self):
        config_map = by_kind(render_docs([]), "ConfigMap")
        self.assertEqual(
            config_map["data"]["mechanic.md"],
            chart_file("files", "agents", "mechanic.md"),
        )


class ImageContract(unittest.TestCase):
    def test_chart_metadata_matches_production_image_tag(self):
        with open(os.path.join(CHART_DIR, "Chart.yaml"), "r", encoding="utf-8") as handle:
            meta = yaml.safe_load(handle)
        with open(os.path.join(CHART_DIR, "values.yaml"), "r", encoding="utf-8") as handle:
            values = yaml.safe_load(handle)
        prod_tag = values["image"]["tag"]
        pilot_tag = values["memoryPilot"]["image"]["tag"]
        self.assertEqual(meta["appVersion"], prod_tag.split("@")[0])
        self.assertEqual(PROD_IMAGE, "%s:%s" % (values["image"]["repository"], prod_tag))
        self.assertEqual(PILOT_IMAGE, "%s:%s" % (values["memoryPilot"]["image"]["repository"], pilot_tag))
        self.assertNotEqual(prod_tag, pilot_tag)

    def test_pilot_template_uses_only_pilot_image_values(self):
        with open(os.path.join(CHART_DIR, "templates", "pilot-deployment.yaml"), "r", encoding="utf-8") as handle:
            pilot_template = handle.read()
        self.assertIn("{{ .Values.memoryPilot.image.repository }}:{{ .Values.memoryPilot.image.tag }}", pilot_template)
        self.assertNotIn("{{ .Values.image.repository }}", pilot_template)

    def test_production_render_uses_v2_image_args_strategy_and_db_env(self):
        deployment = by_kind(render_docs([]), "Deployment")
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        item = container(deployment["spec"]["template"]["spec"], "opencode")
        self.assertEqual(item["image"], PROD_IMAGE)
        self.assertEqual(item["args"], ["serve", "--hostname", "0.0.0.0", "--port", "4096"])
        self.assertEqual(env_entry(item, "OPENCODE_DB")["value"], "opencode.db")

    def test_pilot_render_stays_on_v1_image_and_web_args(self):
        docs = render_docs(PILOT_ARGS)
        item = container(by_kind(docs, "Deployment")["spec"]["template"]["spec"], "opencode")
        self.assertEqual(item["image"], PILOT_IMAGE)
        self.assertEqual(item["args"], ["web", "--hostname", "0.0.0.0", "--port", "4096"])


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

    def test_production_configmap_uses_server_side_apply_only(self):
        self.assertEqual(
            self.config_map["metadata"]["annotations"],
            {"argocd.argoproj.io/sync-options": "ServerSideApply=true"},
        )

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
        self.assertEqual(self.deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(self.deployment["spec"]["replicas"], 1)
        self.assertEqual([item["name"] for item in self.spec["containers"]], ["opencode"])
        opencode = container(self.spec, "opencode")
        self.assertEqual(opencode["image"], PROD_IMAGE)
        self.assertEqual(opencode["args"], ["serve", "--hostname", "0.0.0.0", "--port", "4096"])
        self.assertEqual(env_entry(opencode, "OPENCODE_DB")["value"], "opencode.db")
        zai = env_entry(opencode, "ZHIPU_API_KEY")["valueFrom"]["secretKeyRef"]
        self.assertEqual(zai, {"name": "opencode-zai", "key": "ZHIPU_API_KEY"})
        mounts = {entry["name"]: entry["mountPath"] for entry in opencode["volumeMounts"]}
        self.assertEqual(mounts["artifacts"], "/artifacts")
        self.assertEqual(volume(self.spec, "home"), {"name": "home", "persistentVolumeClaim": {"claimName": "opencode-home"}})
        self.assertEqual(volume(self.spec, "artifacts"), {"name": "artifacts", "persistentVolumeClaim": {"claimName": "opencode-artifacts"}})
        self.assertEqual(volume(self.spec, "openai-auth"), {"name": "openai-auth", "secret": {"secretName": "opencode-openai-auth"}})

    def test_default_render_carries_no_pilot_surfaces(self):
        for forbidden in ("memory-pilot", "opencode-mem", "text-embeddings-inference"):
            self.assertNotIn(forbidden, self.rendered, forbidden)

    def test_opencode_json_uses_migrated_kimi_provider(self):
        cfg = json.loads(self.config_map["data"]["opencode.json"])
        self.assertEqual(cfg["model"], "kimi-code-plan-cn/k3")
        self.assertEqual(cfg["enabled_providers"], ["kimi-code-plan-cn", "minimax-coding-plan", "openai", "zai-coding-plan"])
        self.assertEqual(cfg["provider"], {"kimi-code-plan-cn": {"options": {"apiKey": "{env:KIMI_API_KEY}"}}})
        self.assertNotIn("kimi-for-coding", cfg["provider"])
        self.assertNotIn("kimi-for-coding", json.dumps(cfg))

    def test_kimi_agent_headers_use_migrated_provider(self):
        expected = {"kimi.md": ("kimi-code-plan-cn/k3", "low"), "kimi-256k.md": ("kimi-code-plan-cn/k3-256k", "high"), "docs-writer.md": ("kimi-code-plan-cn/k3-256k", "high"), "release-engineer.md": ("kimi-code-plan-cn/k3-256k", "high")}
        for key, (model, variant) in expected.items():
            parts = self.config_map["data"][key].split("---\n", 2)
            self.assertEqual(len(parts), 3, key)
            header = parts[1]
            self.assertEqual(header.count("model: %s\n" % model), 1, key)
            self.assertEqual(header.count("variant: %s\n" % variant), 1, key)
            self.assertNotIn("kimi-for-coding", header, key)

    def test_kimi_secret_env_ref_unchanged(self):
        opencode = container(self.spec, "opencode")
        kimi = env_entry(opencode, "KIMI_API_KEY")["valueFrom"]["secretKeyRef"]
        self.assertEqual(kimi, {"name": "opencode-kimi", "key": "KIMI_API_KEY"})


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
        self.assertEqual(sorted(self.config_map["data"]), ["AGENTS.md", "opencode-mem.jsonc", "opencode.json"])

    def test_opencode_json_contract(self):
        cfg = json.loads(self.config_map["data"]["opencode.json"])
        self.assertEqual(cfg["$schema"], "https://opencode.ai/config.json")
        self.assertEqual(cfg["model"], "zai-coding-plan/glm-5.3")
        self.assertEqual(cfg["default_agent"], "memory-pilot")
        self.assertEqual(cfg["enabled_providers"], ["zai-coding-plan"])
        self.assertEqual(cfg["provider"]["zai-coding-plan"]["options"]["apiKey"], "{env:ZHIPU_API_KEY}")
        self.assertEqual(cfg["permission"], {"*": "deny", "memory": "allow", "StructuredOutput": "allow"})
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
        self.assertEqual(mem["chatMessage"], {"enabled": True, "maxMemories": 3, "excludeCurrentSession": True, "injectOn": "first"})
        self.assertEqual(mem["compaction"], {"enabled": True, "memoryLimit": 10})
        self.assertEqual(mem["embeddingModel"], EMBEDDING_MODEL)
        self.assertEqual(mem["embeddingDimensions"], 768)
        self.assertTrue(mem["embeddingUseTaskPrefixes"])
        for key in ("memoryProvider", "memoryModel", "memoryApiUrl", "memoryApiKey", "embeddingApiUrl", "embeddingApiKey"):
            self.assertNotIn(key, mem, key)

    def test_agents_md_is_minimal_pilot_instructions(self):
        agents_md = self.config_map["data"]["AGENTS.md"]
        self.assertIn("memory-pilot", agents_md)
        self.assertIn("synthetic", agents_md)
        self.assertIn("not an enforced sandbox", agents_md)

    def test_deployment_is_single_replica_recreate(self):
        self.assertEqual(self.deployment["spec"]["replicas"], 1)
        self.assertEqual(self.deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(self.deployment["spec"]["selector"]["matchLabels"], {"app": PILOT_FULLNAME})
        template_annotations = self.deployment["spec"]["template"]["metadata"]["annotations"]
        self.assertIn("checksum/opencode-server-config", template_annotations)
        deployment_annotations = self.deployment["metadata"]["annotations"]
        self.assertEqual(deployment_annotations["secret.reloader.stakater.com/reload"], "opencode-memory-pilot-provider,opencode-memory-pilot-server-auth")

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
        self.assertEqual(item["image"], PILOT_IMAGE)
        self.assertNotIn("command", item)
        self.assertEqual(item["args"], ["web", "--hostname", "0.0.0.0", "--port", "4096"])
        self.assertEqual(item["startupProbe"], {"tcpSocket": {"port": "http"}, "periodSeconds": 10, "failureThreshold": 120})
        provider_key = env_entry(item, "ZHIPU_API_KEY")["valueFrom"]["secretKeyRef"]
        self.assertEqual(provider_key, {"name": "opencode-memory-pilot-provider", "key": "ZHIPU_API_KEY"})
        server_password = env_entry(item, "OPENCODE_SERVER_PASSWORD")["valueFrom"]["secretKeyRef"]
        self.assertEqual(server_password, {"name": "opencode-memory-pilot-server-auth", "key": "password"})
        env_names = {entry["name"] for entry in item["env"]}
        self.assertNotIn("KIMI_API_KEY", env_names)
        self.assertNotIn("MINIMAX_API_KEY", env_names)
        self.assertEqual(item["ports"], [{"name": "http", "containerPort": 4096}])
        self.assertEqual(item["readinessProbe"], {"tcpSocket": {"port": "http"}})
        self.assertEqual(item["livenessProbe"], {"tcpSocket": {"port": "http"}})
        mounts = {entry["name"]: entry["mountPath"] for entry in item["volumeMounts"]}
        self.assertEqual(mounts, {"home": "/home/opencode", "config": "/home/opencode/.config/opencode", "tmp": "/tmp"})

    def test_no_tei_assets_in_pilot_render(self):
        self.assertEqual([item["name"] for item in self.spec["containers"]], ["opencode"])
        for forbidden in ("text-embeddings-inference", "--model-id", "--revision", "--auto-truncate", "huggingface-hub-cache", "tei-tmp", "8080", "127.0.0.1", "curl"):
            self.assertNotIn(forbidden, self.rendered, forbidden)

    def test_volumes(self):
        names = {item["name"] for item in self.spec["volumes"]}
        self.assertEqual(names, {"home", "config", "config-source", "tmp"})
        self.assertEqual(volume(self.spec, "home"), {"name": "home", "persistentVolumeClaim": {"claimName": PILOT_CLAIM}})
        self.assertEqual(volume(self.spec, "config-source"), {"name": "config-source", "configMap": {"name": PILOT_FULLNAME + "-config", "items": [{"key": "opencode.json", "path": "opencode.json"}, {"key": "opencode-mem.jsonc", "path": "opencode-mem.jsonc"}, {"key": "AGENTS.md", "path": "AGENTS.md"}]}})
        for name in ("config", "tmp"):
            self.assertEqual(volume(self.spec, name), {"name": name, "emptyDir": {}})
        for item in self.spec["volumes"]:
            self.assertNotIn("secret", item)

    def test_all_containers_hardened(self):
        for item in self.spec["initContainers"] + self.spec["containers"]:
            assert_hardened(self, item)

    def test_no_production_content_in_pilot_render(self):
        for forbidden in ("opencode-kimi", "opencode-minimax", "opencode-openai-auth", "opencode-zai", "opencode-home", "opencode-artifacts", "agent-pipe", "grillmaster", "mechanic.md", "mcp-apify", "artifactsExistingClaim"):
            self.assertNotIn(forbidden, self.rendered, forbidden)


class UnsafePilotValues(unittest.TestCase):
    def assert_render_fails(self, extra, needle):
        proc = run_helm(extra)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(needle, proc.stderr)

    def test_enabled_with_production_defaults_fails(self):
        self.assert_render_fails(["--set", "memoryPilot.enabled=true"], "requires fullnameOverride")

    def test_enabled_with_production_claim_fails(self):
        self.assert_render_fails(["--set", "memoryPilot.enabled=true", "--set", "fullnameOverride=" + PILOT_FULLNAME, "--set", "persistence.existingClaim=opencode-home"], "requires persistence.existingClaim")

    def test_enabled_with_empty_claim_fails(self):
        self.assert_render_fails(["--set", "memoryPilot.enabled=true", "--set", "fullnameOverride=" + PILOT_FULLNAME, "--set", "persistence.existingClaim="], "requires persistence.existingClaim")

    def test_enabled_with_near_miss_fullname_fails(self):
        self.assert_render_fails(["--set", "memoryPilot.enabled=true", "--set", "fullnameOverride=opencode-memory-pilots", "--set", "persistence.existingClaim=" + PILOT_CLAIM], "requires fullnameOverride")

    def test_enabled_with_empty_fullname_fails(self):
        self.assert_render_fails(["--set", "memoryPilot.enabled=true", "--set", "fullnameOverride=", "--set", "persistence.existingClaim=" + PILOT_CLAIM], "requires fullnameOverride")

    def test_enabled_with_production_provider_secret_fails(self):
        self.assert_render_fails(["--set", "memoryPilot.enabled=true", "--set", "fullnameOverride=" + PILOT_FULLNAME, "--set", "persistence.existingClaim=" + PILOT_CLAIM, "--set", "memoryPilot.providerSecretName=opencode-zai"], "requires memoryPilot.providerSecretName")

    def test_enabled_with_production_server_secret_fails(self):
        self.assert_render_fails(["--set", "memoryPilot.enabled=true", "--set", "fullnameOverride=" + PILOT_FULLNAME, "--set", "persistence.existingClaim=" + PILOT_CLAIM, "--set", "memoryPilot.serverSecretName=opencode-server-auth"], "requires memoryPilot.serverSecretName")


class WorkflowContract(unittest.TestCase):
    def setUp(self):
        workflow = os.path.join(REPO_ROOT, ".github", "workflows", "helm.yml")
        with open(workflow, "r", encoding="utf-8") as handle:
            self.content = handle.read()

    def test_base_revision_env_uses_event_context(self):
        self.assertIn("PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}", self.content)
        self.assertIn("PUSH_BEFORE_SHA: ${{ github.event.before }}", self.content)
        self.assertNotIn("${{ github.before }}", self.content)

    def test_validation_pipeline_steps_fail_closed(self):
        hygiene = self.content.split("id: hygiene", 1)[1].split("id: helm", 1)[0]
        helm = self.content.split("id: helm", 1)[1].split("name: Report validation", 1)[0]
        for block in (hygiene, helm):
            self.assertIn("shell: bash", block)
            self.assertIn("set -euo pipefail", block)
            self.assertIn("| tee", block)
            self.assertLess(block.index("set -euo pipefail"), block.index("| tee"))


class MakefileContract(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(REPO_ROOT, "Makefile"), "r", encoding="utf-8") as handle:
            self.content = handle.read()

    def test_changed_charts_invocations_print_no_directory(self):
        block = self.content.split("test-changed-charts:", 1)[1].split("test-opencode-server-agents:", 1)[0]
        self.assertEqual(self.content.count("$(MAKE) --no-print-directory changed-charts"), 2)
        self.assertIn('test "$$($(MAKE) --no-print-directory changed-charts BASE_SHA="$$(git rev-parse HEAD)")" = \'[]\'', block)
        self.assertIn("if $(MAKE) --no-print-directory changed-charts BASE_SHA=0000000000000000000000000000000000000001 > /dev/null 2>&1; then", block)

    def test_chart_loop_runs_lint_and_template_separately(self):
        block = self.content.split("\ntest:\n", 1)[1].split("\ntest-changed-charts:\n", 1)[0]
        self.assertIn("set -euo pipefail", block)
        self.assertIn('helm lint --strict "$$chart";', block)
        self.assertIn('helm template test "$$chart" > /dev/null;', block)
        self.assertNotIn('helm lint --strict "$$chart" &&', self.content)


if __name__ == "__main__":
    unittest.main()
