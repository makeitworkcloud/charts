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
PILOT_ARGS = [
    "--set", "memoryPilot.enabled=true",
    "--set", "fullnameOverride=" + PILOT_FULLNAME,
    "--set", "persistence.existingClaim=" + PILOT_CLAIM,
]
BASELINE_QA_ENGINEER = os.path.join("opencode-server", "files", "agents", "qa-engineer.md")
APPROVED_PRIMARY_MODEL_FILES = (
    "career.md",
    "default.md",
    "grillmaster.md",
    "homerepair.md",
    "homesteader.md",
    "lawnmowerman.md",
    "makeitwork.md",
    "teacher.md",
    "xnoto.md",
)
APPROVED_TERRA_MODEL_FILES = (
    "adversarial-code-reviewer.md",
    "cloud-architecture-reviewer.md",
    "devops-engineer.md",
    "infra-security-reviewer.md",
    "recruiter-resume-reviewer.md",
    "terra.md",
)
APPROVED_LUNA_MODEL_FILES = (
    "luna.md",
    "qa-engineer.md",
)
APPROVED_KB_READ_ADDITION_FILES = (
    "career.md",
    "grillmaster.md",
    "homerepair.md",
    "homesteader.md",
    "lawnmowerman.md",
    "makeitwork.md",
    "teacher.md",
    "xnoto.md",
)
KB_READ_ADDITION_ANCHORS = {
    "career.md": b"\n\n## Runtime boundaries\n",
    "grillmaster.md": b"\n\n## Cooking workflow\n",
    "homerepair.md": b"\n\n## Safety and escalation\n",
    "homesteader.md": b"\n\n## Workflow\n",
    "lawnmowerman.md": b"\n\n## Working with images\n",
    "makeitwork.md": b"\n\n## Specialized workflows\n",
    "teacher.md": b"\n\n## Boundaries\n",
    "xnoto.md": b"\n\n## xnoto invariants\n",
}
KB_READ_ADDITION = (
    b"On the first substantive task in a fresh session that could rely on\n"
    b"recalled agent-specific facts or duplicate earlier research, decide first\n"
    b"whether your knowledge home is relevant. When it is, verify current access,\n"
    b"read your own subset README through the same validated default-branch cache\n"
    b"route as other repository reads (standard fallback reasons apply), and then\n"
    b"only the task-relevant documents it cites; if the knowledge home is\n"
    b"unavailable, report that instead of assuming remembered facts. Do not repeat\n"
    b"the index or provenance checks on every turn; recheck them only when the\n"
    b"task, context, or freshness changes. Write only sparse, necessary, verified\n"
    b"durable facts, under the existing subset write policy."
)
APPROVED_KIMI_PROVIDER_MODEL_SUFFIXES = {
    "kimi.md": b"k3",
    "kimi-256k.md": b"k3-256k",
    "docs-writer.md": b"k3-256k",
    "release-engineer.md": b"k3-256k",
}
APPROVED_KIMI_PROVIDER_CONFIG_LINES = (
    (
        b'"model": "kimi-for-coding/k3",',
        b'"model": "kimi-code-plan-cn/k3",',
    ),
    (
        b'"enabled_providers": ["kimi-for-coding",',
        b'"enabled_providers": ["kimi-code-plan-cn",',
    ),
    (
        b'"provider": {"kimi-for-coding": {"options": {"apiKey": "{env:KIMI_API_KEY}"}}},',
        b'"provider": {"kimi-code-plan-cn": {"options": {"apiKey": "{env:KIMI_API_KEY}"}}},',
    ),
)


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
        terra_old = b"model: openai/gpt-5.6-terra\n"
        terra_new = b"model: openai/gpt-6-sol\n"
        for name in APPROVED_TERRA_MODEL_FILES:
            self._replace_frontmatter_line(agents_dir, name, terra_old, terra_new)
        luna_old = b"model: openai/gpt-5.6-luna\n"
        luna_new = b"model: openai/gpt-6-luna\n"
        for name in APPROVED_LUNA_MODEL_FILES:
            self._replace_frontmatter_line(agents_dir, name, luna_old, luna_new)

    def _apply_approved_kb_read_addition(self, baseline_chart):
        agents_dir = os.path.join(baseline_chart, "files", "agents")
        for name in APPROVED_KB_READ_ADDITION_FILES:
            path = os.path.join(agents_dir, name)
            with open(path, "rb") as handle:
                content = handle.read()
            anchor = KB_READ_ADDITION_ANCHORS[name]
            self.assertEqual(content.count(anchor), 1, name)
            content = content.replace(anchor, b"\n\n" + KB_READ_ADDITION + anchor)
            with open(path, "wb") as handle:
                handle.write(content)

    def _apply_approved_provider_migration(self, baseline_chart):
        agents_dir = os.path.join(baseline_chart, "files", "agents")
        old_prefix = b"model: kimi-for-coding/"
        new_prefix = b"model: kimi-code-plan-cn/"
        for name, model_suffix in APPROVED_KIMI_PROVIDER_MODEL_SUFFIXES.items():
            old_line = old_prefix + model_suffix + b"\n"
            new_line = new_prefix + model_suffix + b"\n"
            self._replace_frontmatter_line(agents_dir, name, old_line, new_line)
        config_path = os.path.join(baseline_chart, "files", "opencode.json")
        with open(config_path, "rb") as handle:
            content = handle.read()
        for old_line, new_line in APPROVED_KIMI_PROVIDER_CONFIG_LINES:
            self.assertEqual(content.count(old_line), 1, old_line.decode("ascii"))
            content = content.replace(old_line, new_line)
        with open(config_path, "wb") as handle:
            handle.write(content)

    def _extract_baseline(self, tmp):
        archive = subprocess.run(
            ["git", "archive", "--format=tar", BASELINE_SHA, "opencode-server"],
            capture_output=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(
            archive.returncode, 0, archive.stderr.decode("utf-8", "replace")
        )
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp, filter="data")
        baseline_chart = os.path.join(tmp, "opencode-server")
        self._apply_approved_model_changes(baseline_chart)
        self._apply_approved_kb_read_addition(baseline_chart)
        self._apply_approved_provider_migration(baseline_chart)
        return baseline_chart
