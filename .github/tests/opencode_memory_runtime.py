#!/usr/bin/env python3
"""Bounded validation-only probe for the opencode-memory local-embedding runtime gate.

Runs entirely in ephemeral GitHub CI containers; no production exposure and no
cluster changes. Under test:

  image   ghcr.io/anomalyco/opencode:1.18.29
          @sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8
  plugin  opencode-mem@2.26.0 (release 0c8ed7d54382d9225def8484d691182d46e8552d)

PASS requires ALL of:
  1. The container starts hardened: --user 1000:1000, --read-only,
     --cap-drop ALL, no-new-privileges, tmpfs /tmp, no published ports,
     explicit HOME/XDG env (the stock image has no opencode USER/passwd
     setup). Entrypoint is overridden with /bin/sh -ec: it copies the two
     synthetic configs from a read-only /config-source bind into the writable
     HOME named volume, then execs the pinned `opencode serve --hostname
     127.0.0.1 --port 4096`. This mirrors the production chart's writable
     config seeding instead of a read-only config bind, which differs from
     production and could cause false negatives.
  2. GET /config with x-opencode-directory:/home/opencode initializes the
     plugin via opencode's embedded npm/Arborist (no external bun/npm) and
     the loaded config still carries the pinned plugin spec.
  3. POST /api/memories {content, containerTag} stores one synthetic sentence
     through the real local embedding path (Xenova/nomic-embed-text-v1, 768
     dims) and GET /api/search?q=...&tag=... returns the created id with
     byte-equal content plus a finite numeric similarity >= 0.6.
  4. After docker stop + rm, a replacement container (SAME image, volume,
     config seeding, workdir) returns the SAME memory id and content.

Source-grounded contracts (verified at the pinned releases above):
  - opencode v1.18.29 packages/opencode/src/server/routes/instance/httpapi/
    groups/config.ts + middleware/workspace-routing.ts: GET /config;
    per-request directory from the x-opencode-directory header; Authorization
    middleware is a no-op unless server auth is configured.
  - opencode-mem src/services/web-server.ts: GET /api/search reads `q`
    (+ tag/page/pageSize); POST /api/memories takes {content, containerTag};
    /api/health is readiness only.
  - opencode-mem src/services/web-api-auth.ts + web-server.ts: /api/* except
    /api/health requires webServerApiToken as `Authorization: Bearer ...` or
    x-opencode-mem-token; with no configured token every API call is 401.
  - opencode-mem src/services/api-handlers.ts: handleAddMemory/handleSearch
    always ensureTursoReady + warmup + embedWithTimeout (vector ops execute).
  - opencode-mem src/services/tags.ts + src/config.ts: project tag =
    <containerTagPrefix>_project_ + sha256("path:<cwd>")[:16]; plugin config
    lives at ~/.config/opencode/opencode-mem.jsonc (HOME-derived).

Limitations: autoCapture/autoCleanup/injectProfile disabled; synthetic
API-level probe of local embeddings and container-replacement storage only --
not pod/node DR, conversation extraction, or auto-learning/capture behavior.

Any failure exits nonzero (no green masking). Every non-cleanup subprocess is
deadline-capped (docker pull/prepare included); cleanup runs with fixed
timeouts regardless of the global deadline. Failure classification is
informational only: auth/transport/install causes outrank native suspicion,
native suspicion requires explicit dlopen/shared-library phrases (never a
bare onnxruntime/libsql/musl word), and it is SUSPECTED, not proof -- the
core assertion failure is the gate evidence regardless of cause.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote

IMAGE = (
    "ghcr.io/anomalyco/opencode:1.18.29"
    "@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8"
)
PLUGIN_SPEC = "opencode-mem@2.26.0"
API_TOKEN = "ci-fixture-not-a-secret"  # public synthetic fixture; deliberately not a credential
RUN_ID = uuid.uuid4().hex[:12]
VOLUME = "opencode-mem-ci-" + RUN_ID + "-vol"
CONTAINERS = ("opencode-mem-ci-" + RUN_ID + "-c1", "opencode-mem-ci-" + RUN_ID + "-c2")
WORKDIR = "/home/opencode"
OPENCODE_PORT = 4096
MEM_PORT = 4747  # opencode-mem web server default (src/config.ts)
SENTENCE = "The synthetic runtime probe stores amber-harbor-7f31d2 evidence."
TAG = "opencode_project_" + hashlib.sha256(("path:" + WORKDIR).encode()).hexdigest()[:16]
DEADLINE = time.monotonic() + 19 * 60  # headroom under the 20m job timeout

ENV_ARGS = [
    "-e", "HOME=" + WORKDIR,
    "-e", "XDG_CONFIG_HOME=" + WORKDIR + "/.config",
    "-e", "XDG_CACHE_HOME=" + WORKDIR + "/.cache",
    "-e", "XDG_DATA_HOME=" + WORKDIR + "/.local/share",
]

# Copies ONLY the two synthetic configs from the read-only /config-source bind
# into the writable HOME named volume (uid 1000), then replaces the shell with
# the pinned server. No other files are read; rootfs stays read-only.
CONTAINER_INIT = (
    "mkdir -p " + WORKDIR + "/.config/opencode; "
    "cp /config-source/opencode.json /config-source/opencode-mem.jsonc "
    + WORKDIR + "/.config/opencode/; "
    "exec /usr/local/bin/opencode serve --hostname 127.0.0.1 --port " + str(OPENCODE_PORT)
)

OPENCODE_JSON = {
    "$schema": "https://opencode.ai/config.json",
    "plugin": [PLUGIN_SPEC],
    "enabled_providers": [],
    "permission": {"*": "deny"},
}

MEM_JSONC = {
    "storagePath": WORKDIR + "/.opencode-mem/data",
    "embeddingModel": "Xenova/nomic-embed-text-v1",
    "embeddingDimensions": 768,
    "embeddingUseTaskPrefixes": True,
    "autoCaptureEnabled": False,
    "autoCleanupEnabled": False,
    "injectProfile": False,
    "containerTagPrefix": "opencode",
    "webServerEnabled": True,
    "webServerHost": "127.0.0.1",
    "webServerPort": MEM_PORT,
    "webServerApiToken": API_TOKEN,
    "similarityThreshold": 0.6,
}

AUTH_MARKERS = ("401", "unauthorized")
TRANSPORT_MARKERS = ("timeout", "timed out", "refused", "connection reset", "econnreset")
INSTALL_MARKERS = ("enotfound", "fetch failed", "eresolve", "eacces", "registry", "npm err", "network")
NATIVE_MARKERS = (
    "dlopen",
    "cannot open shared object",
    "error loading shared library",
    "cannot locate symbol",
    "undefined symbol",
    "libc.so",
    "glibc_",
)
ERROR_HINTS = (
    "error", "fail", "exception", "cannot", "dlopen", "shared object",
    "undefined symbol", "native", "module", "abort",
)
SENSITIVE_HINTS = (
    "token", "auth", "bearer", "secret", "password", "authorization",
    "api-key", "api_key", "apikey", "env",
)


class Fail(Exception):
    pass


def phase(message: str) -> None:
    print("[phase] " + message, flush=True)


def bounded(text: str, limit: int = 1500) -> str:
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


def run(cmd, timeout, check=False, enforce_deadline=True):
    """Bounded subprocess wrapper. Runtime calls are capped to the remaining
    global deadline (docker pull/prepare included); cleanup and failure-path
    evidence gathering pass enforce_deadline=False so they still run."""
    if enforce_deadline:
        remaining = DEADLINE - time.monotonic()
        if remaining <= 0:
            raise Fail("global deadline exhausted before: " + " ".join(cmd[:6]))
        timeout = min(timeout, remaining)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)
    except subprocess.TimeoutExpired:
        raise Fail("subprocess timeout: " + " ".join(cmd[:6])) from None
    except subprocess.CalledProcessError as error:
        tail = bounded(((error.stdout or "") + (error.stderr or "")).strip(), 400)
        raise Fail("command rc=%d: %s :: %s" % (error.returncode, " ".join(cmd[:6]), tail)) from None


def cap(requested: float) -> float:
    """Deadline-bounded float timeout for a single API call."""
    remaining = DEADLINE - time.monotonic()
    if remaining <= 0:
        raise Fail("global deadline exhausted")
    return max(0.1, min(requested, remaining))


def require_remaining(seconds: float) -> None:
    if DEADLINE - time.monotonic() < seconds:
        raise Fail("global deadline too close (need %.0fs)" % seconds)


def wget(container, url, *, headers=(), post=None, timeout):
    timeout = cap(timeout)  # float seconds; subprocess accepts floats
    cmd = ["docker", "exec", container, "wget", "-qO-", "-T", str(max(1, int(timeout)))]
    for key, value in headers:
        cmd += ["--header", key + ": " + value]
    if post is not None:
        cmd += ["--header", "Content-Type: application/json", "--post-data", post]
    cmd.append(url)
    result = run(cmd, timeout + 25)  # run() re-caps to the remaining deadline
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def plugin_present(data) -> bool:
    """The pinned plugin spec must actually be in the loaded config plugin list."""
    plugins = data.get("plugin") if isinstance(data, dict) else None
    if not isinstance(plugins, list):
        return False
    for spec in plugins:
        if spec == PLUGIN_SPEC:
            return True
        if isinstance(spec, list) and spec and spec[0] == PLUGIN_SPEC:
            return True
    return False


def wait_json(container, url, *, headers, allow, window, label, per_call=20):
    """Retry an in-container wget until JSON passing `allow` arrives within `window`s."""
    end = time.monotonic() + window
    last = "no attempt"
    while time.monotonic() < end and time.monotonic() < DEADLINE:
        rc, out, err = wget(
            container,
            url,
            headers=headers,
            timeout=min(per_call, end - time.monotonic()),
        )
        if rc == 0:
            try:
                data = json.loads(out)
            except ValueError:
                last = "non-JSON response: " + bounded(out, 200)
            else:
                if allow(data):
                    return data
                last = "rejected response: " + bounded(out, 300)
        else:
            last = "wget rc=%d %s" % (rc, bounded(err or out, 200))
        time.sleep(5)
    raise Fail(label + " not satisfied within " + str(window) + "s; last: " + last)


def api_call(container, path, *, post, timeout, label):
    rc, out, err = wget(
        container,
        "http://127.0.0.1:%d%s" % (MEM_PORT, path),
        headers=(("Authorization", "Bearer " + API_TOKEN),),
        post=post,
        timeout=timeout,
    )
    if rc != 0:
        raise Fail(label + " transport failure: " + bounded(err or out, 400))
    try:
        return json.loads(out)
    except ValueError:
        raise Fail(label + " non-JSON response: " + bounded(out, 400)) from None


def search(container, *, window, per_call):
    path = "/api/search?q=" + quote(SENTENCE) + "&tag=" + TAG + "&pageSize=20"
    return wait_json(
        container,
        "http://127.0.0.1:%d%s" % (MEM_PORT, path),
        headers=(("Authorization", "Bearer " + API_TOKEN),),
        allow=lambda data: data.get("success") is True,
        window=window,
        label="search",
        per_call=per_call,
    )


def start_container(name, cfg_dir) -> None:
    run(
        [
            "docker", "run", "-d", "--name", name,
            "--user", "1000:1000", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--tmpfs", "/tmp",
            "--entrypoint", "/bin/sh",
            *ENV_ARGS,
            "-v", VOLUME + ":" + WORKDIR,
            "-v", str(cfg_dir) + ":/config-source:ro",
            "-w", WORKDIR, IMAGE,
            "-ec", CONTAINER_INIT,
        ],
        timeout=120,
        check=True,
    )


def assert_hit(payload, memory_id, label) -> float:
    if payload.get("success") is not True:
        raise Fail(label + " success!=true: " + bounded(json.dumps(payload), 400))
    items = (payload.get("data") or {}).get("items") or []
    hits = [i for i in items if i.get("type") == "memory" and i.get("id") == memory_id]
    if not hits:
        raise Fail(label + ": id " + memory_id + " absent: " + bounded(json.dumps(payload), 400))
    hit = hits[0]
    if hit.get("content") != SENTENCE:
        raise Fail(label + ": content mismatch for " + memory_id)
    similarity = hit.get("similarity")
    if isinstance(similarity, bool) or not isinstance(similarity, (int, float)):
        raise Fail(label + ": missing numeric similarity for " + memory_id)
    similarity = float(similarity)
    if not math.isfinite(similarity):
        raise Fail(label + ": non-finite similarity for " + memory_id)
    if similarity < 0.6:
        raise Fail(label + ": similarity %.4f below 0.6 for %s" % (similarity, memory_id))
    return similarity


def diagnostics(container) -> str:
    logs = run(["docker", "logs", "--tail", "150", container], timeout=30, enforce_deadline=False)
    return ((logs.stdout or "") + (logs.stderr or "")).strip()


def relevant_lines(logs):
    """Error-looking lines only; never auth/token/env lines; no config dumps."""
    kept = []
    for line in logs.splitlines():
        low = line.lower()
        if any(hint in low for hint in SENSITIVE_HINTS):
            continue
        if any(hint in low for hint in ERROR_HINTS):
            kept.append(line.strip())
    return kept[:40]


def classify_failure(detail: str) -> str:
    low = detail.lower()
    if any(marker in low for marker in AUTH_MARKERS):
        return "AUTH (401/unauthorized) -- NOT compatibility evidence"
    if any(marker in low for marker in TRANSPORT_MARKERS):
        return "TRANSPORT/TIMEOUT -- NOT compatibility evidence"
    if any(marker in low for marker in INSTALL_MARKERS):
        return "INSTALL/DEPENDENCY -- NOT compatibility evidence"
    if any(marker in low for marker in NATIVE_MARKERS):
        return ("NATIVE_LOAD_SUSPECTED (explicit dlopen/shared-library phrase) -- "
                "informational only, not proof; the failed assertion is the gate "
                "evidence regardless of cause")
    return "UNCLASSIFIED (runtime error) -- not classified as native load failure"


def main() -> int:
    cfg_dir = None
    try:
        phase("preflight: docker availability")
        run(["docker", "version"], timeout=60, check=True)
        cfg_dir = Path(tempfile.mkdtemp(prefix="opencode-mem-ci-"))
        (cfg_dir / "opencode.json").write_text(json.dumps(OPENCODE_JSON, indent=2) + "\n", encoding="utf-8")
        (cfg_dir / "opencode-mem.jsonc").write_text(json.dumps(MEM_JSONC, indent=2) + "\n", encoding="utf-8")
        os.chmod(cfg_dir / "opencode.json", 0o644)
        os.chmod(cfg_dir / "opencode-mem.jsonc", 0o644)
        os.chmod(cfg_dir, 0o755)  # mkdtemp 0700 would block runtime uid 1000 on the ro bind

        phase("prepare named volume ownership (root container, cap CHOWN only, non-recursive)")
        run(["docker", "volume", "create", VOLUME], timeout=60, check=True)
        run(
            [
                "docker", "run", "--rm",
                "--user", "0:0", "--cap-drop", "ALL", "--cap-add", "CHOWN",
                "--security-opt", "no-new-privileges", "--read-only",
                "--entrypoint", "/bin/sh",
                "-v", VOLUME + ":" + WORKDIR,
                IMAGE, "-c", "chown 1000:1000 " + WORKDIR,
            ],
            timeout=180,
            check=True,
        )

        phase("start container 1 (hardened, read-only, cap-drop ALL, no published ports)")
        start_container(CONTAINERS[0], cfg_dir)

        phase("initialize plugin via GET /config (x-opencode-directory; npm install window)")
        wait_json(
            CONTAINERS[0],
            "http://127.0.0.1:%d/config" % OPENCODE_PORT,
            headers=(("x-opencode-directory", WORKDIR),),
            allow=plugin_present,
            window=330,
            label="opencode /config",
        )

        phase("wait for opencode-mem web server readiness (/api/health only)")
        wait_json(
            CONTAINERS[0],
            "http://127.0.0.1:%d/api/health" % MEM_PORT,
            headers=(),
            allow=lambda data: data.get("success") is True and data.get("status") == "ok",
            window=150,
            label="/api/health",
        )

        phase("POST /api/memories: store synthetic sentence (local embedding executes)")
        require_remaining(320)
        add = api_call(
            CONTAINERS[0],
            "/api/memories",
            post=json.dumps({"content": SENTENCE, "containerTag": TAG}),
            timeout=300,
            label="add memory",
        )
        if add.get("success") is not True:
            raise Fail("add success!=true: " + bounded(json.dumps(add), 400))
        memory_id = (add.get("data") or {}).get("id")
        if not memory_id:
            raise Fail("add returned no memory id: " + bounded(json.dumps(add), 400))
        print("  created memory id: " + memory_id, flush=True)

        phase("GET /api/search?q=...&tag=...: vector search must return the created id")
        similarity1 = assert_hit(search(CONTAINERS[0], window=180, per_call=60), memory_id, "search C1")
        print("  similarity C1: %.4f" % similarity1, flush=True)

        phase("graceful replacement: stop and remove container 1")
        run(["docker", "stop", "-t", "30", CONTAINERS[0]], timeout=90, check=True)
        run(["docker", "rm", CONTAINERS[0]], timeout=60, check=True)

        phase("start replacement container (SAME image/volume/config/workdir)")
        start_container(CONTAINERS[1], cfg_dir)
        wait_json(
            CONTAINERS[1],
            "http://127.0.0.1:%d/config" % OPENCODE_PORT,
            headers=(("x-opencode-directory", WORKDIR),),
            allow=plugin_present,
            window=240,
            label="opencode /config (replacement)",
        )
        wait_json(
            CONTAINERS[1],
            "http://127.0.0.1:%d/api/health" % MEM_PORT,
            headers=(),
            allow=lambda data: data.get("success") is True and data.get("status") == "ok",
            window=120,
            label="/api/health (replacement)",
        )

        phase("replacement read: same persisted memory id and content required")
        similarity2 = assert_hit(search(CONTAINERS[1], window=300, per_call=150), memory_id, "search C2")
        print("  similarity C2: %.4f" % similarity2, flush=True)

        phase("PASS: local embeddings executed; memory survived container replacement")
        print("  image=" + IMAGE, flush=True)
        print("  plugin=" + PLUGIN_SPEC + " tag=" + TAG, flush=True)
        return 0
    except Fail as error:
        detail = str(error)
        print("[fail] " + bounded(detail), flush=True)
        for container in CONTAINERS:
            state = run(
                ["docker", "inspect", "-f", "{{.State.Status}}", container],
                timeout=30,
                enforce_deadline=False,
            )
            if (state.stdout or "").strip():
                lines = relevant_lines(diagnostics(container))
                if lines:
                    printed = bounded("\n".join(lines))
                    print("[container-logs] " + container + " (filtered): " + printed, flush=True)
                    detail += "\n" + printed
        print("[classification] " + classify_failure(detail), flush=True)
        return 1
    finally:
        # Fixed timeouts with enforce_deadline=False: an expired global deadline
        # must never block cleanup of the probe's own containers and volume.
        phase("cleanup: remove only the two probe containers and the named volume")
        for container in CONTAINERS:
            try:
                run(["docker", "rm", "-f", container], timeout=60, enforce_deadline=False)
            except Fail:
                pass
        try:
            run(["docker", "volume", "rm", "-f", VOLUME], timeout=60, enforce_deadline=False)
        except Fail:
            pass
        if cfg_dir is not None:
            shutil.rmtree(cfg_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
