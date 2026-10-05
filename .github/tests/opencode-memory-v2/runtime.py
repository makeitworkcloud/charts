#!/usr/bin/env python3
"""Test-only CI fixture: opencode-mem v2 plugin in the stock OpenCode container.

Synthetic data on a disposable runner; a PASS covers only what README.md
lists. Security rationale: UUID-named disposable resources; non-root,
read-only app containers with every capability dropped and no-new-privileges;
no published ports, socket, or checkout mounts; env allow-list; sanitized,
bounded diagnostics; scoped cleanup whose failure fails the gate.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote_plus

IMAGE = ("ghcr.io/anomalyco/opencode:2.0.22@"
         "sha256:11f2b6c96d380867387fbee390c06cb47efffd9fdc37009b4cd40795b45dad19")
PLATFORM = "linux/amd64"
OPENCODE_VERSION = "2.0.22"
PLUGIN_SPEC = "opencode-mem@2.28.3"
PLUGIN_ID = "opencode-mem"
PLUGIN_VERSION = "2.28.3"
PLUGIN_RELEASE = "a24d79e34857aed9c5e708f5325714e6948bbfa7"

# Public synthetic fixture values only (never production material).
BASIC_USER = "opencode"
BASIC_PASSWORD = "opencode-ci-public-password"
MEM_TOKEN = "opencode-mem-ci-public-token"
# Project-scope tag shape parsed by plugin src/services/memory-scope.ts at PLUGIN_RELEASE.
CONTAINER_TAG = "sm_project_0c1f1a2b3c4d5e6f"

HOME_PATH = "/home/opencode"
MEM_STORAGE = HOME_PATH + "/.opencode-mem"
SERVER_PORT = 4096
MEM_PORT = 4747
APP_USER = "1000:1000"
APP_UID = "1000"
MEMORY_CONTENT = ("OpenCode memory v2 CI fixture synthetic memory: the amber "
                  "lighthouse catalogs quartz sparrow reports.")
SIMILARITY_THRESHOLD = 0.6

GLOBAL_DEADLINE_S = 22 * 60     # reserves three job minutes beyond diagnostics and cleanup
DOCKER_TIMEOUT_S = 180
PULL_TIMEOUT_S = 600
PREP_TIMEOUT_S = 300
HTTP_TIMEOUT_S = 10             # read-only GET probes
POST_TIMEOUT_S = 600            # single embedding POST; cold model download allowed
EXEC_MARGIN_S = 15              # docker exec timeout = wget budget + margin
POLL_INTERVAL_S = 3.0
STOP_TIMEOUT_S = 30
DIAGNOSTIC_BUDGET_S = 60        # separate budgets; <=5 min combined with cleanup
CLEANUP_BUDGET_S = 240
LOG_TAIL_LINES = 40
LOG_TAIL_BYTES = 8192

APP_ENV = [
    ("HOME", HOME_PATH),
    ("XDG_CONFIG_HOME", HOME_PATH + "/.config"),
    ("XDG_CACHE_HOME", HOME_PATH + "/.cache"),
    ("XDG_DATA_HOME", HOME_PATH + "/.local/share"),
    ("OPENCODE_DB", "opencode.db"),  # bare filename; resolved inside XDG data dir (canonical)
    ("OPENCODE_PASSWORD", BASIC_PASSWORD),
]

OPENCODE_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "plugins": [PLUGIN_SPEC],
    "enabled_providers": [],     # V1-compatible provider disable (approved plan)
    "permissions": [{"action": "*", "resource": "*", "effect": "deny"}],
}

# Plugin defaults pinned explicitly; absolute local storage under the persistent
# home volume; no provider/model/embedding API keys; userProfileAnalysisInterval
# deliberately absent (0 is invalid).
MEM_CONFIG = {
    "storagePath": MEM_STORAGE,
    "embeddingModel": "Xenova/nomic-embed-text-v1",
    "embeddingDimensions": 768,
    "similarityThreshold": SIMILARITY_THRESHOLD,
    "autoCaptureEnabled": False, "autoCleanupEnabled": False,
    "injectProfile": False, "userProfileAutoCleanupEnabled": False,
    "userProfileValidationEnabled": False,
    "chatMessage": {"enabled": False},
    "compaction": {"enabled": False},
    "autoUpdate": False,
    "databaseEncryptionEnabled": False,
    "webServerEnabled": True,
    "webServerHost": "127.0.0.1",
    "webServerPort": MEM_PORT,
    "webServerApiToken": MEM_TOKEN,
}

_REDACTIONS = [
    (re.compile(r"(?i)authorization\s*:\s*[^\s]+.*"), "authorization: [redacted]"),
    (re.compile(r"(?i)bearer\s+[^\s]+"), "bearer [redacted]"),
    (re.compile(r"(?i)x-opencode-mem-token\s*:\s*[^\s]+"), "x-opencode-mem-token: [redacted]"),
    (re.compile(r"(?i)\b(token|secret|password|passwd|credential|api[_-]?key)\b\s*[=:]\s*[^\s]+"),
     r"\1=[redacted]"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(PASSWORD|TOKEN|SECRET|API_?KEY|CREDENTIAL)[A-Z0-9_]*)=\S+"),
     r"\1=[redacted]"),
    (re.compile(r"(?i)[a-z][a-z0-9+.\-]*://[^\s/:@]+:[^\s/@]+@"), "[redacted-url]://"),
]

_DIAG_ALLOW = re.compile(
    r"(?i)\b(error|fail|fatal|panic|exception|eaddr|econn|timeout|timed out|denied|exit|crash)\b")

def sanitize(text):
    """Redact auth headers, tokens, passwords, env-style secrets, URL credentials."""
    out = text if isinstance(text, str) else repr(text)
    for pattern, repl in _REDACTIONS:
        out = pattern.sub(repl, out)
    return out

def clip(text, limit=LOG_TAIL_BYTES):
    text = text or ""
    if len(text) <= limit:
        return text
    return "...[clipped]..." + text[-limit:]

class StageError(Exception):
    """Failure attributed to a lifecycle stage (see README failure-stage table)."""

    def __init__(self, stage, message):
        super().__init__(f"[{stage}] {clip(sanitize(message))}")
        self.stage = stage

_now = time.monotonic
_sleep = time.sleep

class PluginFailedError(StageError):
    pass

def _subprocess_execute(args, timeout):
    try:
        proc = subprocess.run(["docker"] + list(args), capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise StageError("transport", f"docker {' '.join(map(str, args[:3]))} timed out after {timeout}s")
    return proc.returncode, proc.stdout or "", proc.stderr or ""

class Docker:
    """Docker CLI adapter bounded by an optional deadline: every operation uses
    min(requested, remaining) so slow steps consume, never exceed, the budget."""

    def __init__(self, execute=None, deadline=None):
        self.execute = execute or _subprocess_execute
        self.deadline = deadline

    def set_deadline(self, deadline):
        self.deadline = deadline

    def budget(self, requested, stage="transport"):
        if self.deadline is None:
            return requested
        remaining = self.deadline - _now()
        if remaining <= 0:
            raise StageError(stage, "time budget exhausted before docker operation")
        return min(requested, remaining)

    def run(self, args, timeout=DOCKER_TIMEOUT_S, stage="transport"):
        rc, out, err = self.execute(list(args), self.budget(timeout, stage))
        if rc != 0:
            raise StageError(stage, f"docker {list(args[:4])} rc={rc}: {clip(sanitize(err or out))}")
        return out

    def try_run(self, args, timeout=DOCKER_TIMEOUT_S, stage="transport"):
        return self.execute(list(args), self.budget(timeout, stage))

    def exists(self, name, kind="container"):
        args = (["volume", "inspect"] if kind == "volume" else ["container", "inspect"]) + [name]
        rc, _out, err = self.execute(args, self.budget(DOCKER_TIMEOUT_S, "cleanup"))
        if rc == 0:
            return True
        if "no such" in (err or "").lower():
            return False
        raise StageError("cleanup", f"{kind} inspect {name} rc={rc}: {clip(sanitize(err))}")

class Resources:
    """Scoped registry; names are tracked BEFORE creation so a docker CLI
    timeout (which may still have created the object) cannot orphan them."""

    def __init__(self, docker):
        self.docker = docker
        self.containers = []
        self.volumes = []

    def track_container(self, name):
        self.containers.append(name)

    def track_volume(self, name):
        self.volumes.append(name)

    def _remove_container(self, name):
        if not self.docker.exists(name, "container"):
            return
        try:
            self.docker.run(["stop", "-t", str(STOP_TIMEOUT_S), name], stage="cleanup")
        except StageError:
            pass  # still attempt rm -f below; it tears down running containers too
        self.docker.run(["rm", "-f", name], stage="cleanup")

    def _remove_volume(self, name):
        if self.docker.exists(name, "volume"):
            self.docker.run(["volume", "rm", "-f", name], stage="cleanup")

    def cleanup(self):
        errors = []
        for remover, names in ((self._remove_container, self.containers),
                               (self._remove_volume, self.volumes)):
            for name in names:
                try:
                    remover(name)
                except StageError as exc:
                    errors.append(str(exc))
        if errors:
            raise StageError("cleanup", "; ".join(errors))

def _require_dict(obj, stage, what):
    if not isinstance(obj, dict):
        raise StageError(stage, f"{what}: expected JSON object, got {type(obj).__name__}")
    return obj

def check_info_payload(obj):
    _require_dict(obj, "startup", "GET /api/info")
    version = obj.get("version")
    if version != OPENCODE_VERSION:
        raise StageError("startup", f"server version {version!r} != pinned {OPENCODE_VERSION!r}")
    for key in ("pid", "urls", "paths"):
        if key not in obj:
            raise StageError("startup", f"GET /api/info missing {key!r}")
    return obj

def check_plugin_payload(obj):
    """Exact invariants: id, package source, pinned target/version, active state, HOME location envelope."""
    _require_dict(obj, "registration", "GET /api/plugin")
    location = obj.get("location")
    if not isinstance(location, dict) or location.get("directory") != HOME_PATH:
        raise StageError("registration", f"location envelope missing or directory != {HOME_PATH!r}")
    entries = obj.get("data")
    if not isinstance(entries, list):
        raise StageError("registration", "plugin payload malformed (wrapped or missing 'data' list)")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        source = source if isinstance(source, dict) else {}
        target, version = source.get("target"), source.get("version")
        state = entry.get("state")
        source_matches = source.get("type") == "package" and target in (PLUGIN_ID, PLUGIN_SPEC)
        if source_matches and isinstance(state, dict) and state.get("status") == "failed":
            raise PluginFailedError("registration", f"plugin {target!r} failed: {state.get('error')!s}")
        if entry.get("id") != PLUGIN_ID:
            continue
        if version is not None and version != PLUGIN_VERSION:
            raise StageError("registration", f"plugin resolved version mismatch: {version!r}")
        if source.get("type") != "package":
            raise StageError("registration", f"unexpected plugin source type {source.get('type')!r}")
        if target != PLUGIN_SPEC and not (target == PLUGIN_ID and version == PLUGIN_VERSION):
            raise StageError("registration", f"plugin target/version mismatch: {target!r}@{version!r}")
        if not isinstance(state, dict) or "status" not in state:
            raise StageError("registration", "plugin entry missing state.status")
        if state.get("status") != "active":
            detail = state.get("error") or state.get("status")
            raise StageError("registration", f"plugin state {state.get('status')!r}: {clip(sanitize(str(detail)))}")
        return entry
    inventory = []
    for entry in entries[:8]:
        if isinstance(entry, dict):
            source = entry.get("source")
            source = source if isinstance(source, dict) else {}
            state = entry.get("state")
            state = state if isinstance(state, dict) else {}
            inventory.append({"id": entry.get("id"), "type": source.get("type"),
                              "target": source.get("target"), "version": source.get("version"),
                              "status": state.get("status")})
    raise StageError("registration", f"{PLUGIN_ID} not present in plugin inventory: {inventory!r}")

def check_add_response(obj):
    _require_dict(obj, "storage", "POST /api/memories")
    if obj.get("success") is not True:
        raise StageError("storage", f"add not successful: {clip(sanitize(str(obj.get('error') or obj)))}")
    data = obj.get("data")
    if not isinstance(data, dict):
        raise StageError("storage", "add payload malformed (wrapped or missing 'data')")
    memory_id = data.get("id")
    if not isinstance(memory_id, str) or not memory_id:
        raise StageError("storage", f"add returned invalid id {memory_id!r}")
    return memory_id

def check_search_response(obj, memory_id, content):
    _require_dict(obj, "embedding", "GET /api/search")
    if obj.get("success") is not True:
        raise StageError("embedding", f"search not successful: {clip(sanitize(str(obj.get('error') or obj)))}")
    data = obj.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise StageError("embedding", "search payload malformed (wrapped or missing 'data.items')")
    match = None
    for item in data["items"]:
        if isinstance(item, dict) and item.get("id") == memory_id:
            match = item
            break
    if match is None:
        raise StageError("storage", f"memory id not found among {len(data['items'])} search results")
    if match.get("type") != "memory":
        raise StageError("storage", f"search item type {match.get('type')!r} != 'memory'")
    if match.get("content") != content:
        raise StageError("storage", "recalled content differs from stored content")
    similarity = match.get("similarity")
    # Lower bound only: cosine similarity >= threshold; no unsupported upper bound.
    if isinstance(similarity, bool) or not isinstance(similarity, (int, float)):
        raise StageError("embedding", f"similarity missing or non-numeric: {similarity!r}")
    if not math.isfinite(similarity):
        raise StageError("embedding", "similarity is not finite (NaN/inf)")
    if similarity < SIMILARITY_THRESHOLD:
        raise StageError("embedding", f"similarity {similarity} < threshold {SIMILARITY_THRESHOLD}")
    return similarity

def check_mem_health(obj):
    _require_dict(obj, "registration", "GET /api/health")
    if obj.get("success") is not True or obj.get("status") != "ok":
        raise StageError("registration", f"plugin web health not ok: {clip(sanitize(str(obj)))}")
    return obj

def _parse_json(raw, path):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise StageError("transport", f"non-JSON response from {path}: {exc}; body={clip(sanitize(str(raw)))}")

class ContainerHttp:
    """HTTP via `docker exec wget` (stock busybox wget); no ports published.
    GETs use 10s; the single embedding POST gets a dedicated long budget and is
    never retried."""

    def __init__(self, docker):
        self.docker = docker
        self.posts = 0
        self.get_paths = []
        self.post_payloads = []

    def _wget(self, cname, url, headers, body=None, timeout=HTTP_TIMEOUT_S):
        args = ["exec", cname, "wget", "-q", "-O", "-", "-T", str(int(timeout))]
        for header in headers:
            args += ["--header", header]
        if body is not None:
            args += ["--header", "Content-Type: application/json", "--post-data", body]
        args.append(url)
        return self.docker.run(args, timeout=timeout + EXEC_MARGIN_S)

    def server_get(self, cname, path):
        cred = base64.b64encode(f"{BASIC_USER}:{BASIC_PASSWORD}".encode()).decode()
        raw = self._wget(cname, f"http://127.0.0.1:{SERVER_PORT}{path}",
                         [f"Authorization: Basic {cred}"])
        return _parse_json(raw, path)

    def mem_get(self, cname, path):
        self.get_paths.append(path)
        raw = self._wget(cname, f"http://127.0.0.1:{MEM_PORT}{path}",
                         [f"Authorization: Bearer {MEM_TOKEN}"])
        return _parse_json(raw, path)

    def mem_post_json(self, cname, path, payload):
        self.posts += 1
        self.post_payloads.append(payload)
        raw = self._wget(cname, f"http://127.0.0.1:{MEM_PORT}{path}",
                         [f"Authorization: Bearer {MEM_TOKEN}"],
                         body=json.dumps(payload), timeout=POST_TIMEOUT_S)
        return _parse_json(raw, path)

def write_seed_files(seed_dir):
    """World-readable seed (tempfile defaults 0700 would block the capability-less
    root preparer from reading the read-only bind)."""
    root = Path(seed_dir)
    for name, payload in (("opencode.json", OPENCODE_CONFIG), ("opencode-mem.jsonc", MEM_CONFIG)):
        path = root / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o644)
    os.chmod(root, 0o755)

def create_volume(docker, res, name):
    res.track_volume(name)  # track before create: a CLI timeout may still create it
    docker.run(["volume", "create", name], stage="startup")

def pull_and_verify_image(docker):
    docker.run(["image", "pull", "--platform", PLATFORM, IMAGE], timeout=PULL_TIMEOUT_S, stage="startup")

    def field(fmt):
        return docker.run(["image", "inspect", IMAGE, "--format", fmt]).strip()

    os_name, arch = field("{{.Os}}"), field("{{.Architecture}}")
    image_id = field("{{.Id}}")
    digests = json.loads(field("{{json .RepoDigests}}") or "[]")
    digest = IMAGE.split("@", 1)[1]
    if os_name != "linux" or arch not in ("amd64", "x86_64"):
        raise StageError("startup", f"unexpected image platform {os_name}/{arch}")
    if not image_id.startswith("sha256:"):
        raise StageError("startup", "image .Id missing sha256 digest")
    if not any(str(entry).endswith(digest) for entry in digests):
        raise StageError("startup", f"pinned digest absent from RepoDigests: {digests}")

def seed_volume(docker, res, prep_name, seed_dir, cfg_vol, home_vol=None):
    """Root preparer (same image, UID 0, CHOWN only, offline) seeds a fresh
    config volume. Image ENTRYPOINT is `opencode`, so sh is forced via
    --entrypoint; chmod precedes chown (CAP_FOWNER is dropped). home_vol=None
    (replacement) leaves the retained home volume unmounted."""
    res.track_container(prep_name)
    steps = ["mkdir -p /home/opencode/.config/opencode",
             "cp /seed/opencode.json /seed/opencode-mem.jsonc /home/opencode/.config/opencode/"]
    if home_vol is not None:
        steps += ["chmod -R u+rwX /home/opencode", "chown -R 1000:1000 /home/opencode"]
    else:
        steps += ["chmod -R u+rwX /home/opencode/.config", "chown -R 1000:1000 /home/opencode/.config"]
    args = ["run", "--rm", "--platform", PLATFORM, "--name", prep_name,
            "--user", "0:0", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--cap-add", "CHOWN",
            "--security-opt", "no-new-privileges", "--tmpfs", "/tmp",
            "-v", f"{seed_dir}:/seed:ro",
            "-v", f"{cfg_vol}:/home/opencode/.config"]
    if home_vol is not None:
        args += ["-v", f"{home_vol}:/home/opencode"]
    args += ["--entrypoint", "sh", IMAGE, "-c", " && ".join(steps)]
    docker.run(args, timeout=PREP_TIMEOUT_S, stage="startup")

def app_run_args(name, home_vol, cfg_vol, seed_dir, offline):
    args = ["run", "-d", "--platform", PLATFORM, "--name", name,
            "--user", APP_USER, "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--tmpfs", "/tmp",
            "--workdir", HOME_PATH]
    args += ["--network", "none" if offline else "bridge"]
    for key, value in APP_ENV:
        args += ["-e", f"{key}={value}"]
    args += ["-v", f"{home_vol}:{HOME_PATH}",
             "-v", f"{cfg_vol}:{HOME_PATH}/.config",
             "-v", f"{seed_dir}/opencode.json:{HOME_PATH}/.config/opencode/opencode.json:ro",
             "--entrypoint", "opencode",
             IMAGE,
             "serve", "--hostname", "127.0.0.1", "--port", str(SERVER_PORT)]
    return args

def _inspect_field(docker, name, fmt):
    return docker.run(["container", "inspect", name, "--format", fmt], stage="startup").strip()

def verify_security(docker, name, expect_network):
    """Selected inspect fields only (never Config.Env) plus in-container uid."""
    expectations = [
        ("user", _inspect_field(docker, name, "{{.Config.User}}"), APP_USER),
        ("readonly-rootfs", _inspect_field(docker, name, "{{.HostConfig.ReadonlyRootfs}}"), "true"),
        ("cap-drop", _inspect_field(docker, name, "{{json .HostConfig.CapDrop}}"), '["ALL"]'),
        ("no-new-privileges",
         "no-new-privileges" in _inspect_field(docker, name, "{{json .HostConfig.SecurityOpt}}"), True),
        ("port-bindings", _inspect_field(docker, name, "{{json .HostConfig.PortBindings}}"), "{}"),
        ("network", _inspect_field(docker, name, "{{.HostConfig.NetworkMode}}"), expect_network)]
    for label, actual, expected in expectations:
        if actual != expected:
            raise StageError("startup", f"{name} security check {label!r}: {actual!r} != {expected!r}")
    cap_add = _inspect_field(docker, name, "{{json .HostConfig.CapAdd}}")
    if cap_add not in ("null", "[]"):
        raise StageError("startup", f"{name} unexpected granted capabilities: {cap_add}")
    uid = docker.run(["exec", name, "id", "-u"], stage="startup").strip()
    if uid != APP_UID:
        raise StageError("startup", f"{name} runs as uid {uid!r}, expected {APP_UID}")

def add_memory(http, cname):
    if http.posts:
        raise StageError("storage", "refusing duplicate memory POST (one-shot by design)")
    payload = {"content": MEMORY_CONTENT, "containerTag": CONTAINER_TAG}
    return check_add_response(http.mem_post_json(cname, "/api/memories", payload))

def search_verify(http, cname, memory_id):
    path = ("/api/search?q=" + quote_plus(MEMORY_CONTENT)
            + "&tag=" + quote_plus(CONTAINER_TAG) + "&page=1&pageSize=10")
    return check_search_response(http.mem_get(cname, path), memory_id, MEMORY_CONTENT)

def wait_until(label, fn, deadline, interval=POLL_INTERVAL_S):
    last = None
    while True:
        if _now() >= deadline:
            stage = last.stage if last is not None else "startup"
            raise StageError(stage, f"{label}: deadline exhausted before check; last error: {last}")
        try:
            result = fn()
        except StageError as exc:
            last = exc
            if isinstance(exc, PluginFailedError):
                raise
            if _now() >= deadline:
                raise StageError(exc.stage, f"{label}: deadline exhausted; last error: {exc}")
            _sleep(min(interval, max(0, deadline - _now())))
            continue
        if _now() >= deadline:
            raise StageError("startup", f"{label}: result arrived after deadline; rejected")
        return result

def bootstrap(http, cname, deadline):
    wait_until("server readiness",
               lambda: check_info_payload(http.server_get(cname, "/api/info")), deadline)
    wait_until("plugin registration",
               lambda: check_plugin_payload(
                   http.server_get(cname, "/api/plugin?location[directory]=/home/opencode")), deadline)
    wait_until("plugin web health",
               lambda: check_mem_health(http.mem_get(cname, "/api/health")), deadline)

def diagnostics(docker, res):
    """Bounded, allow-listed, sanitized failure lines only (docker logs writes
    native errors to stderr; stdout and stderr are merged). No raw logs."""
    docker.set_deadline(_now() + DIAGNOSTIC_BUDGET_S)
    chunks = []
    for name in res.containers:
        try:
            _rc, out, err = docker.try_run(["logs", "--tail", str(LOG_TAIL_LINES), name])
        except StageError:
            continue
        merged = sanitize(((out or "") + "\n" + (err or "")))
        hits = [line for line in merged.splitlines() if _DIAG_ALLOW.search(line)]
        if hits:
            chunks.append(f"--- {name} failure lines (sanitized, bounded) ---\n"
                          + clip("\n".join(hits)))
    return "\n".join(chunks)

def main():
    docker = Docker()
    res = Resources(docker)
    http = ContainerHttp(docker)
    run_id = uuid.uuid4().hex[:10]
    home_vol = f"ocmemci-home-{run_id}"
    cfg_vols = [f"ocmemci-cfg-{run_id}-c1", f"ocmemci-cfg-{run_id}-c2"]
    app_names = [f"ocmemci-app-{run_id}-c1", f"ocmemci-app-{run_id}-c2"]
    prep_names = [f"ocmemci-prep-{run_id}-c1", f"ocmemci-prep-{run_id}-c2"]
    seed_dir = None
    lifecycle_ok = False
    try:
        deadline = _now() + GLOBAL_DEADLINE_S  # global budget starts before pull
        docker.set_deadline(deadline)
        print(f"fixture run {run_id}: {IMAGE} ({PLATFORM})")
        print(f"plugin {PLUGIN_SPEC} (release {PLUGIN_RELEASE})")
        pull_and_verify_image(docker)
        for volume in [home_vol, *cfg_vols]:
            create_volume(docker, res, volume)
        seed_dir = tempfile.mkdtemp(prefix="ocmemci-seed-")
        write_seed_files(seed_dir)

        print("stage: primary container (cold network: plugin + embedding model fetch)")
        seed_volume(docker, res, prep_names[0], seed_dir, cfg_vols[0], home_vol=home_vol)
        res.track_container(app_names[0])
        docker.run(app_run_args(app_names[0], home_vol, cfg_vols[0], seed_dir, offline=False),
                   stage="startup")
        verify_security(docker, app_names[0], "bridge")
        primary = app_names[0]
        bootstrap(http, primary, deadline)

        print("stage: storage + embedding (single POST, dedicated budget, no retry)")
        memory_id = add_memory(http, primary)
        print(f"memory id: {memory_id}")
        similarity = search_verify(http, primary, memory_id)
        print(f"primary recall similarity: {similarity}")

        print("stage: graceful stop + removal of primary")
        docker.run(["stop", "-t", str(STOP_TIMEOUT_S), primary], stage="startup")
        docker.run(["rm", primary], stage="startup")

        print("stage: offline replacement (fresh seeded config volume, persistent home)")
        seed_volume(docker, res, prep_names[1], seed_dir, cfg_vols[1], home_vol=None)
        res.track_container(app_names[1])
        docker.run(app_run_args(app_names[1], home_vol, cfg_vols[1], seed_dir, offline=True),
                   stage="startup")
        verify_security(docker, app_names[1], "none")
        replacement = app_names[1]
        bootstrap(http, replacement, deadline)
        if http.posts != 1:
            raise StageError("storage", f"expected exactly one memory POST, performed {http.posts}")
        recall = search_verify(http, replacement, memory_id)
        print(f"offline replacement recall similarity: {recall}")
        lifecycle_ok = True
    except StageError as exc:
        print(f"FAIL {exc}")
        tail = diagnostics(docker, res)
        if tail:
            print(tail)
    except Exception as exc:  # unexpected: still sanitized, bounded, cleaned up
        print(f"FAIL [internal] {clip(sanitize(repr(exc)))}")
        tail = diagnostics(docker, res)
        if tail:
            print(tail)
    finally:
        if seed_dir:
            try:
                shutil.rmtree(seed_dir)
            except OSError as exc:
                print(f"FAIL [cleanup] seed removal: {clip(sanitize(str(exc)))}")
                lifecycle_ok = False
        docker.set_deadline(_now() + CLEANUP_BUDGET_S)  # separate budget, not per-op 180s
        try:
            res.cleanup()
        except StageError as exc:
            print(f"FAIL {exc}")
            lifecycle_ok = False
        else:
            print("cleanup: ok (scoped resources removed)")
        if lifecycle_ok:  # PASS only when lifecycle AND cleanup succeeded
            print("PASS: opencode-mem v2 runtime fixture")
    return 0 if lifecycle_ok else 1

if __name__ == "__main__":
    sys.exit(main())
