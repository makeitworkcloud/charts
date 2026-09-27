import glob
import hashlib
import io
import json
import os
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
PROD_IMAGE = "ghcr.io/anomalyco/opencode:1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8"
EMBEDDING_MODEL = "Xenova/nomic-embed-text-v1"
PILOT_FULLNAME = "opencode-memory-pilot"
PILOT_CLAIM = "opencode-memory-pilot-home"
PILOT_ARGS = ["--set", "memoryPilot.enabled=true", "--set", "fullnameOverride=" + PILOT_FULLNAME, "--set", "persistence.existingClaim=" + PILOT_CLAIM]
BASELINE_QA_ENGINEER = os.path.join("opencode-server", "files", "agents", "qa-engineer.md")
APPROVED_PRIMARY_MODEL_FILES = ("career.md", "default.md", "grillmaster.md", "homerepair.md", "homesteader.md", "lawnmowerman.md", "makeitwork.md", "teacher.md", "xnoto.md")
APPROVED_TERRA_MODEL_FILES = ("adversarial-code-reviewer.md", "cloud-architecture-reviewer.md", "devops-engineer.md", "infra-security-reviewer.md", "recruiter-resume-reviewer.md", "terra.md")
APPROVED_LUNA_MODEL_FILES = ("luna.md", "qa-engineer.md")
APPROVED_KNOWLEDGE_FILES = ("career.md", "grillmaster.md", "homerepair.md", "homesteader.md", "lawnmowerman.md", "makeitwork.md", "teacher.md", "xnoto.md")
# Literal policy additions, not snippets derived from the current prompts.
KNOWLEDGE_FIRST_PARAGRAPHS = {
    "career.md": "Before substantive owner-specific fit, resume, or interview advice, presume your authorized `docs/agents/career/` knowledge home is relevant. Verify private access and read its subset README and entry instructions through the validated default-branch cache route (or verified-SHA GitHub fallback) before deciding which details matter. Follow nested indexes to confirmed background, goals, constraints, prior decisions and corrections for the active role or application; do not invent qualifications. If the index does not resolve the topic, use bounded topical search, never bulk-read journals or the whole corpus. Retrieve before personalized recommendations or external research whose applicability depends on career facts; apply the constraints, not just a README citation.",
    "teacher.md": "Before substantive owner-specific teaching advice, presume your authorized `docs/agents/teacher/` knowledge home is relevant. Verify private access and read its subset README and entry instructions through the validated default-branch cache route (or verified-SHA GitHub fallback) before deciding which details matter. Follow nested indexes to select the correct teaching context and recorded audience, objectives, source restrictions, delivery needs, prior decisions, and corrections. If the index does not resolve the topic, use bounded topical search, never bulk-read journals or the whole corpus. Retrieve before personalized recommendations or external research whose applicability depends on teaching context; apply constraints, not just a README citation.",
    "grillmaster.md": "Before substantive owner-specific cooking advice, presume your authorized `docs/agents/grillmaster/` knowledge home is relevant. Verify private access and read its subset README and entry instructions through the validated default-branch cache route (or verified-SHA GitHub fallback) before deciding which details matter; follow nested indexes to task-relevant canonical facts, constraints, prior decisions, and corrections. Read the equipment and preferences, sources and research, and applicable technique-default records before proposing a cook; retain their existing source hierarchy and technique rules. If an index does not resolve the topic, make a bounded topical search, not a bulk read of journals or the whole corpus. Retrieve before personalized recommendations or external research whose applicability depends on owner facts; apply the constraints, not just a README citation.",
    "homerepair.md": "Before substantive owner-specific repair advice, presume your authorized `docs/agents/homerepair/` knowledge home is relevant. Verify private access and read its subset README and entry instructions through the validated default-branch cache route (or verified-SHA GitHub fallback) before deciding which details matter. Follow nested indexes to match the actual asset in `assets.md` and the prior job in `jobs/README.md` and its relevant record before diagnosis or asking about prior repairs; apply trade guidance, canonical constraints, decisions, and corrections. If the index does not resolve the topic, use bounded topical search, never bulk-read journals or the whole corpus. Retrieve before personalized recommendations or external research whose applicability depends on household facts; apply constraints, not just a README citation.",
    "homesteader.md": "Before substantive owner-specific homestead advice, presume your authorized `docs/agents/homesteader/` knowledge home is relevant. Verify private access and read its subset README and entry instructions through the validated default-branch cache route (or verified-SHA GitHub fallback) before deciding which details matter. Explicitly read `workspace/AGENTS.md` and `workspace/property.md` as remote documents; they are not automatically loaded. For planting or land use, follow nested indexes to relevant canonical site, climate, water, and project records, including prior decisions and corrections. Establish feasibility and prerequisites before instructions; never substitute a generic region for verified property context. If the index does not resolve the topic, search topically within a bounded scope, never bulk-read journals or the whole corpus. Retrieve before personalized recommendations or external research whose applicability depends on property facts; apply constraints, not just a README citation.",
    "lawnmowerman.md": "Before substantive owner-specific diagnosis or parts advice, presume your authorized `docs/agents/lawnmowerman/` knowledge home is relevant. Verify private access and read its subset README and entry instructions via the validated default-branch cache route (or verified-SHA GitHub fallback) before deciding which details matter. Follow nested indexes to the actual machine and engine records, service history, canonical constraints, decisions, and corrections; match the machine and engine before diagnosis or parts selection, and verify specifications and part references with the manufacturer. If the index does not resolve the topic, search topically within a bounded scope, never bulk-read journals or the whole corpus. Retrieve before personalized recommendations or external research whose applicability depends on owner facts; apply the constraints, not just a README citation.",
    "makeitwork.md": "Before substantive owner-specific repository or advisory planning, presume your authorized `docs/agents/makeitwork/` knowledge home is relevant. Verify private access and read its subset README and entry instructions through the validated default-branch cache route (or verified-SHA GitHub fallback) before deciding which details matter. Follow nested indexes to relevant recorded decisions, exceptions, ownership, canonical constraints, and prior corrections; verify actual implementation against the canonical repository, since knowledge is not desired state. If the index does not resolve the topic, use bounded topical search, never bulk-read journals or the whole corpus. Retrieve before personalized recommendations or external research whose applicability depends on owner facts; apply constraints, not just a README citation.",
    "xnoto.md": "Before substantive owner-specific repository or advisory planning, presume your authorized `docs/agents/xnoto/` knowledge home is relevant. Verify private access and read its subset README and entry instructions through the validated default-branch cache route (or verified-SHA GitHub fallback) before deciding which details matter. Follow nested indexes to relevant recorded decisions, exceptions, ownership, canonical constraints, and prior corrections; verify actual implementation against the canonical repository, since knowledge is not desired state. If the index does not resolve the topic, use bounded topical search, never bulk-read journals or the whole corpus. Retrieve before personalized recommendations or external research whose applicability depends on owner facts; apply constraints, not just a README citation.",
}
COMMON_KNOWLEDGE_FOLLOWUP = "Distinguish owner-confirmed facts from dated observations, research estimates, and superseded guidance. Resolve decision-changing conflicts against current evidence or ask the smallest owner question; never invent a reconciliation. Ask only for facts still missing after retrieval or requiring confirmation. Reuse verified context on unchanged followups; refresh newly relevant records on task, subject, or agent change and reestablish missing evidence after compaction or resume. Recheck access and provenance on context, task, or freshness changes per existing validated cache routing, not every turn. If knowledge is unavailable, disclose it and withhold owner-specific conclusions dependent on it; label general information explicitly and never bypass private access. Give imminent safety advice without waiting for retrieval. Cite concise privacy-safe source path and revision and explain how constraints shaped the answer, without verbatim private records or unrelated external inputs. This read policy grants no additional write or mutation authority."
KNOWLEDGE_FOLLOWUPS = {
    "grillmaster.md": "Distinguish owner-confirmed facts from dated observations, research estimates, and superseded guidance. Resolve decision-changing conflicts against current evidence or ask the smallest owner question; never invent a reconciliation. Ask only for facts still missing after retrieval or requiring confirmation. Reuse verified context on unchanged followups, but refresh newly relevant records on a task, subject, or agent change; after compaction or resume reestablish missing evidence. Recheck access and provenance on context, task, or freshness changes per the existing validated cache routing, not every turn. If the knowledge home is unavailable, disclose that and withhold owner-specific conclusions dependent on it; label any general information explicitly and never bypass private access. Give imminent safety advice without waiting for retrieval. Cite a concise privacy-safe source path and revision and explain how constraints shaped the answer, without verbatim private content or unrelated external inputs. This read policy grants no additional write or mutation authority.",
    "homesteader.md": "Distinguish owner-confirmed facts from dated observations, research estimates, and superseded guidance. Resolve decision-changing conflicts against current evidence or ask the smallest owner question; never invent a reconciliation. Ask only for facts still missing after retrieval or requiring confirmation. Reuse verified context on unchanged followups, but refresh newly relevant records on a task, subject, or agent change; after compaction or resume reestablish missing evidence. Recheck access and provenance on context, task, or freshness changes per existing validated cache routing, not every turn. If knowledge is unavailable, disclose that and withhold owner-specific conclusions dependent on it; label any general information explicitly and never bypass private access. Give imminent safety advice without waiting for retrieval. Cite concise privacy-safe source path and revision and explain how constraints shaped the answer, without raw private records or unrelated external inputs. This read policy grants no additional write or mutation authority.",
}
DEFAULT_ROUTING = """## Owner-context routing

For an owner-specific domain question, identify the authorized relevant specialist and knowledge context before advice. The generic `default` agent has no autonomous `agent-knowledge` subtree or write scope. Retrieve only relevant records within verified read authority, starting with the authorized entry instructions and following bounded indexes, or suggest switching to the specialist if that scope is unavailable; do not pretend a handoff occurred or silently replace missing owner context with generic advice. Before personalized recommendations or owner-dependent external research, apply confirmed facts, constraints, prior decisions, and corrections; distinguish dated observations, estimates, and superseded guidance. Resolve decision-changing conflicts with current evidence or ask the smallest owner question, never invent a reconciliation. Ask only what remains missing after retrieval or requires confirmation. Reuse verified context for unchanged followups; on a task, subject, or agent change refresh newly relevant records, and after compaction or resume reestablish missing evidence. Recheck private access and cache provenance on context, task, or freshness changes per existing routing, not every turn. If knowledge is unavailable, disclose it, withhold dependent owner-specific conclusions, and explicitly label any general information; never bypass private access. Give imminent safety advice without waiting for retrieval. Cite a concise privacy-safe path and revision and explain how constraints shaped advice; do not dump private records or send them as unrelated external inputs. This routing grants no additional write or mutation authority."""
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
        primary_new = b"mode: primary\nmodel: openai/gpt-6-astra\n"
        for name in APPROVED_PRIMARY_MODEL_FILES:
            self._replace_frontmatter_line(agents_dir, name, primary_old, primary_new)
        for name in APPROVED_TERRA_MODEL_FILES:
            self._replace_frontmatter_line(agents_dir, name, b"model: openai/gpt-5.6-terra\n", b"model: openai/gpt-6-sol\n")
        for name in APPROVED_LUNA_MODEL_FILES:
            self._replace_frontmatter_line(agents_dir, name, b"model: openai/gpt-5.6-luna\n", b"model: openai/gpt-6-luna\n")

    def _apply_approved_knowledge_policy(self, baseline_chart):
        agents_dir = os.path.join(baseline_chart, "files", "agents")
        for name in APPROVED_KNOWLEDGE_FILES + ("default.md",):
            path = os.path.join(agents_dir, name)
            with open(path, "rb") as handle:
                content = handle.read()
            anchor = b"\n\n## Primary operating rules\n"
            self.assertEqual(content.count(anchor), 1, name)
            if name == "default.md":
                addition = DEFAULT_ROUTING
            else:
                addition = ("## Knowledge-first advice\n\n" + KNOWLEDGE_FIRST_PARAGRAPHS[name] + "\n\n" + KNOWLEDGE_FOLLOWUPS.get(name, COMMON_KNOWLEDGE_FOLLOWUP))
            content = content.replace(anchor, b"\n\n" + addition.encode("utf-8") + anchor)
            if name == "homesteader.md":
                for old, new in ((HOMESTEADER_CONFIDENTIALITY_OLD, HOMESTEADER_CONFIDENTIALITY_NEW), (HOMESTEADER_WORKFLOW_OLD, HOMESTEADER_WORKFLOW_NEW)):
                    before = old.encode("utf-8")
                    self.assertEqual(content.count(before), 1, old)
                    content = content.replace(before, new.encode("utf-8"))
            with open(path, "wb") as handle:
                handle.write(content)

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

    def _extract_baseline(self, tmp):
        archive = subprocess.run(["git", "archive", "--format=tar", BASELINE_SHA, "opencode-server"], capture_output=True, cwd=REPO_ROOT)
        self.assertEqual(archive.returncode, 0, archive.stderr.decode("utf-8", "replace"))
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp, filter="data")
        baseline_chart = os.path.join(tmp, "opencode-server")
        self._apply_approved_model_changes(baseline_chart)
        self._apply_approved_knowledge_policy(baseline_chart)
        self._apply_approved_provider_migration(baseline_chart)
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

    def test_approved_agent_model_changes_are_only_expected_source_changes(self):
        with tempfile.TemporaryDirectory(prefix="opencode-server-baseline-") as tmp:
            baseline_chart = self._extract_baseline(tmp)
            baseline_agents = os.path.join(baseline_chart, "files", "agents")
            current_agents = os.path.join(CHART_DIR, "files", "agents")
            self.assertEqual(sorted(os.listdir(current_agents)), sorted(os.listdir(baseline_agents)))
            for name in sorted(os.listdir(baseline_agents)):
                with open(os.path.join(baseline_agents, name), "rb") as handle:
                    baseline_bytes = handle.read()
                with open(os.path.join(current_agents, name), "rb") as handle:
                    current_bytes = handle.read()
                if name == "qa-engineer.md":
                    self.assertEqual(current_bytes, baseline_bytes + b"\n")
                else:
                    self.assertEqual(current_bytes, baseline_bytes, name)


class KnowledgeFirstPolicyContract(unittest.TestCase):
    def test_named_primary_agents_have_early_bounded_policy(self):
        agents_dir = os.path.join(CHART_DIR, "files", "agents")
        for name in sorted(os.listdir(agents_dir)):
            with open(os.path.join(agents_dir, name), "r", encoding="utf-8") as handle:
                text = handle.read()
            expected = 1 if name in APPROVED_KNOWLEDGE_FILES else 0
            self.assertEqual(text.count("## Knowledge-first advice"), expected, name)
            self.assertNotIn("On the first substantive task in a fresh session", text, name)
            if not expected:
                continue
            section = text.split("## Knowledge-first advice\n", 1)[1].split("\n## Primary operating rules\n", 1)[0]
            self.assertLess(text.index("## Knowledge-first advice"), text.index("## Primary operating rules"), name)
            for marker in ("presume your authorized", "subset README", "entry instructions", "nested indexes", "bounded", "Retrieve before personalized", "apply", "owner-confirmed facts", "dated observations", "superseded guidance", "decision-changing conflicts", "after retrieval", "unchanged followups", "agent change", "compaction or resume", "Recheck access and provenance", "not every turn", "unavailable", "withhold owner-specific conclusions", "general information explicitly", "imminent safety advice", "privacy-safe source path and revision", "no additional write or mutation authority"):
                self.assertIn(marker.lower(), section.lower(), (name, marker))

    def test_role_specific_prerequisites_and_default_routing(self):
        markers = {
            "career.md": ("confirmed background, goals, constraints", "fit, resume, or interview"),
            "teacher.md": ("correct teaching context", "audience, objectives, source restrictions, delivery needs"),
            "grillmaster.md": ("equipment and preferences", "sources and research", "technique-default"),
            "homerepair.md": ("assets.md", "jobs/README.md", "before diagnosis"),
            "homesteader.md": ("workspace/AGENTS.md", "workspace/property.md", "not automatically loaded", "site, climate, water", "feasibility and prerequisites", "minimal pertinent context", "advice alone is not authorization"),
            "lawnmowerman.md": ("actual machine and engine", "service history", "manufacturer"),
            "makeitwork.md": ("advisory planning", "decisions, exceptions, ownership", "canonical repository"),
            "xnoto.md": ("advisory planning", "decisions, exceptions, ownership", "canonical repository"),
            "default.md": ("## Owner-context routing", "no autonomous `agent-knowledge` subtree or write scope", "suggest switching to the specialist", "do not pretend a handoff occurred", "imminent safety advice"),
        }
        for name, phrases in markers.items():
            with open(os.path.join(CHART_DIR, "files", "agents", name), "r", encoding="utf-8") as handle:
                text = handle.read().lower()
            for phrase in phrases:
                self.assertIn(phrase.lower(), text, (name, phrase))
        with open(os.path.join(CHART_DIR, "files", "agents", "default.md"), "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertEqual(text.count("## Owner-context routing"), 1)
        self.assertLess(text.index("## Owner-context routing"), text.index("## Primary operating rules"))

    def test_docs_describe_policy_not_enforcement(self):
        for relative in (os.path.join("docs", "agent-instruction-architecture.md"), "README.md"):
            with open(os.path.join(CHART_DIR, relative), "r", encoding="utf-8") as handle:
                text = " ".join(handle.read().split())
            self.assertIn("policy-directed attempt", text, relative)
            self.assertIn("not a guaranteed automatic enforcement mechanism", text, relative)
            self.assertIn("knowledge isolation and backup/restore automation remain deferred", text, relative)
            self.assertIn("actual retrieval and application", text, relative)


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
        self.assertEqual(item["image"], PROD_IMAGE)
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
        for forbidden in ("opencode-kimi", "opencode-minimax", "opencode-openai-auth", "opencode-zai", "opencode-home", "opencode-artifacts", "agent-pipe", "grillmaster", "mcp-apify", "artifactsExistingClaim"):
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
