#!/usr/bin/env python3
"""CI-only stock-image init-volume feasibility; candidate B is the sole runtime gate."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from urllib.parse import quote
import uuid

from diagnostics import run_cases

IMAGE = "ghcr.io/anomalyco/opencode:1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8"
HOME = "/home/opencode"
CONFIG = HOME + "/.config/opencode"
PLUGINS = ["context-mode@1.0.169", "opencode-mem@2.26.0"]
TOOLS = {"memory", "ctx_execute", "ctx_batch_execute", "ctx_index", "ctx_search", "ctx_stats"}
TOKEN = "ci-fixture-not-a-secret"
SENTENCE = "The synthetic runtime probe stores amber-harbor-7f31d2 evidence."
TAG = "opencode_project_" + hashlib.sha256(("path:" + HOME).encode()).hexdigest()[:16]
PREFIX = "opencode-init-" + uuid.uuid4().hex
FIXTURES = str(Path(__file__).resolve().parent)
VOLUMES, CONTAINERS = [], []
DEADLINE = time.monotonic() + 600  # Shared setup budget: pull, identity, provisioning, inspection.
REPORT = {"arms": {}, "context_host_dispatch": "not tested; registration only"}
HARDEN = ["--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--ulimit=core=0",
          "--tmpfs=/tmp:rw,size=512m,mode=1777"]
ENV = ["-e", "HOME=" + HOME, "-e", "XDG_CONFIG_HOME=" + HOME + "/.config",
       "-e", "XDG_CACHE_HOME=" + HOME + "/.cache", "-e", "XDG_DATA_HOME=" + HOME + "/.local/share",
       "-e", "XDG_STATE_HOME=" + HOME + "/.local/state",
       "-e", "CONTEXT_MODE_DIR=" + HOME + "/.local/share/context-mode",
       "-e", "PATH=/opt/runtime/usr/bin:/opt/runtime/bin:/usr/local/bin:/usr/bin:/bin",
       "-e", "LD_LIBRARY_PATH=/opt/runtime/lib:/opt/runtime/usr/lib"]
OPENCODE = {"plugin": PLUGINS, "enabled_providers": [], "permission": {"*": "deny"}, "mcp": {}}
MEMORY = {
    "storagePath": HOME + "/.opencode-mem/data", "embeddingModel": "Xenova/nomic-embed-text-v1",
    "embeddingDimensions": 768, "embeddingUseTaskPrefixes": True,
    "autoCaptureEnabled": False, "autoCleanupEnabled": False, "injectProfile": False,
    "userProfileAutoCleanupEnabled": False, "userProfileValidationEnabled": False,
    "chatMessage": {"enabled": False}, "compaction": {"enabled": False},
    "containerTagPrefix": "opencode", "webServerEnabled": True, "webServerHost": "127.0.0.1",
    "webServerPort": 4747, "webServerApiToken": TOKEN, "similarityThreshold": 0.6,
}


class Failure(Exception):
    pass


def native_evidence(text):
    # Only bounded, relevant synthetic crash context; never a raw log dump.
    text = text[-65536:]
    phrases = [p for p in ["error loading shared library", "undefined symbol", "symbol not found",
               "invalid ELF", "Exec format error", "Permission denied", "Read-only file system",
               "certificate", "ENOTFOUND", "ECONNREFUSED", "timed out"] if p.lower() in text.lower()]
    symbols = re.findall(r"(?:undefined symbol[: ]+|Error relocating [^\n:]+: )([A-Za-z_][A-Za-z0-9_]{0,100})", text)
    relevant = re.compile(r"assert|panic|crash|illegal.?instruction|segmentation|\bbun\b|onnx|plugin|^\s*at ", re.I)
    sensitive = re.compile(r"authorization|bearer|token|password|secret|cookie|environment|config(?:uration)?\s*[:=]", re.I)
    lines = [sanitize(line)[:384] for line in text.splitlines()[-80:]
             if relevant.search(line) and not sensitive.search(line)]
    return {"markers": phrases, "unresolved_symbols": sorted(set(symbols))[:12],
            "crash_lines": lines[-16:]}


def sanitize(text):
    detail = text[-8192:]
    detail = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', detail)
    detail = re.sub(r'(?i)\b(?:https?|ftp|file)://[^\s<>"\x27]+', '[url]', detail)
    detail = re.sub(r'(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+', '[credential]', detail)
    detail = re.sub(r'(?i)\b(?:password|passwd|token|api[_-]?key|authorization|secret|cookie)["\x27]?\s*[:=]\s*(?:"[^"]*"|\x27[^\x27]*\x27|[^\s,;]+)', '[credential]', detail)
    detail = re.sub(r'\b(?:sk-|ghp_|github_pat_|hf_)[A-Za-z0-9_-]+', '[credential]', detail)
    detail = re.sub(r'\b[^\s:@/]+:[^\s@/]+@[^\s/]+', '[credential]', detail)
    detail = re.sub(r'\?[^\s<>"\x27]+', '[query]', detail)
    detail = re.sub(r'(?:[A-Za-z]:[\\/]|~/|\.\.?/|/)[^\s<>"\x27()]+', '[path]', detail)
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', detail)[:768]


def run(args, timeout=60, check=True, cleanup=False, data=None):
    budget = timeout if cleanup else min(timeout, DEADLINE - time.monotonic())
    if budget <= 0:
        raise Failure("phase deadline exhausted")
    try:
        result = subprocess.run(["docker", *args], input=data, text=True, capture_output=True, timeout=budget)
    except (subprocess.TimeoutExpired, OSError):
        raise Failure("container command timeout or unavailable") from None
    if check and result.returncode:
        raise Failure("docker " + args[0] + " failed rc=" + str(result.returncode) + " "
                      + json.dumps({"error": sanitize(result.stderr), **native_evidence(result.stderr + result.stdout)}))
    return result


def observe(name):
    evidence = {}
    try:
        template = '{' + ','.join('"' + key + '":{{json .State.' + key + '}}'
                                 for key in ["Status", "Running", "ExitCode", "OOMKilled", "Error"]) + '}'
        result = run(["inspect", "--format", template, name], timeout=15, check=False, cleanup=True)
        evidence["inspect_returncode"] = result.returncode
        if result.returncode:
            return evidence
        state = json.loads(result.stdout)
        state["Error"] = sanitize(state["Error"])
        evidence["state"] = state
        if not state["Running"]:
            return evidence
        # Stock shell builtins only; no Node, raw maps, environment, or config.
        script = '''mapped=unavailable
if test -r /proc/1/maps; then
    mapped=false
    while IFS= read -r line; do
        case "$line" in *"/opt/runtime/lib/libgcompat.so.0"*) mapped=true; break ;; esac
    done < /proc/1/maps
fi
printf 'gcompat %s\\n' "$mapped"
for file in /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.events /sys/fs/cgroup/memory.events.local /sys/fs/cgroup/memory/memory.max_usage_in_bytes /sys/fs/cgroup/memory/memory.oom_control; do
    test -r "$file" || continue
    count=0
    while read -r key value rest; do
        count=$((count + 1))
        test "$count" -le 16 || break
        printf '%s %s %s\\n' "${file##*/}" "$key" "$value"
    done < "$file"
done'''
        result = run(["exec", name, "/bin/sh", "-c", script], timeout=15, check=False, cleanup=True)
        evidence["shell_returncode"] = result.returncode
        for line in result.stdout[:4096].splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0] == "gcompat" and fields[1] in ("true", "false", "unavailable"):
                evidence["host_gcompat_mapped"] = {"true": True, "false": False, "unavailable": None}[fields[1]]
            elif len(fields) == 2 and fields[0] in ("memory.peak", "memory.current", "memory.max_usage_in_bytes") and fields[1].isdigit():
                evidence.setdefault("cgroup", {})[fields[0]] = int(fields[1])
            elif len(fields) == 3 and fields[0] in ("memory.events", "memory.events.local", "memory.oom_control") and fields[1] in ("oom", "oom_kill", "oom_group_kill", "under_oom") and fields[2].isdigit():
                evidence.setdefault("cgroup", {})[fields[0] + "." + fields[1]] = int(fields[2])
    except (Failure, ValueError, KeyError, TypeError) as error:
        evidence["unavailable"] = type(error).__name__
    return evidence


def volume(suffix):
    name = PREFIX + "-" + suffix
    VOLUMES.append(name)
    run(["volume", "create", name])
    return name


def helper(args, command, timeout=120, data=None, cleanup=False):
    name = PREFIX + "-helper-" + str(len(CONTAINERS))
    CONTAINERS.append(name)
    return run(["run", "--rm", "-i", "--name", name, "--pull=never", "--platform=linux/amd64",
                *HARDEN, *args, "--entrypoint=/bin/sh", IMAGE, "-ec", command],
               timeout=timeout, data=data, cleanup=cleanup)


def request(name, port, route, post=None, timeout=30):
    headers = {"x-opencode-directory": HOME}
    if port == 4747:
        headers["Authorization"] = "Bearer " + TOKEN
    if post is not None:
        headers["Content-Type"] = "application/json"
    # Per-exec client override does not modify PID 1 or the container's config.
    result = run(["exec", "-i", "-e", "LD_PRELOAD=", name, "node", "/probe/http.mjs"], timeout=timeout + 10,
                 data=json.dumps({"port": port, "route": route, "post": post,
                                  "headers": headers, "timeout": timeout}))
    envelope = json.loads(result.stdout)
    CURRENT["last_request"] = {"route": route.split("?")[0], "status": envelope["status"],
                               "error": envelope["error"]}
    if envelope["error"] is not None or not isinstance(envelope["status"], int) or not 200 <= envelope["status"] < 300:
        return None
    return envelope["body"]


def wait(name, port, route, accept, window=300):
    end = min(DEADLINE, time.monotonic() + window)
    while time.monotonic() < end:
        payload = request(name, port, route, timeout=max(1, min(25, int(end - time.monotonic()))))
        if payload is not None and accept(payload):
            return payload
        if run(["inspect", "--format", "{{.State.Status}}", name]).stdout.strip() != "running":
            raise Failure("application exited before readiness")
        time.sleep(2)
    raise Failure("readiness deadline exhausted")


def elf(runtime, inspect, home=None, cleanup=False):
    mounts = ["--network=none", "--user=1000:1000", "-v", runtime + ":/opt/runtime:ro",
              "-v", inspect + ":/opt/inspect:ro", "-e", "LD_LIBRARY_PATH=/opt/inspect/lib:/opt/inspect/usr/lib"]
    if home is None:
        command = ("/opt/inspect/usr/bin/readelf -l /usr/local/bin/opencode; printf 'NODE_ELF\n'; "
                   "/opt/inspect/usr/bin/readelf -l /opt/runtime/usr/bin/node; "
                   "/opt/inspect/usr/bin/readelf --dyn-syms --wide /opt/runtime/lib/libgcompat.so.0")
    else:
        mounts += ["-v", home + ":" + HOME + ":ro"]
        command = ("find " + HOME + "/.cache/opencode/packages/opencode-mem@2.26.0/node_modules "
                   "-type f -path '*/linux/x64/*' \\( -name 'libonnxruntime.so*' -o -name 'onnxruntime_binding.node' \\) "
                   "-exec /opt/inspect/usr/bin/readelf -d '{}' ';'")
    output = helper(mounts, command, cleanup=cleanup).stdout
    if home is not None:
        return {"needed": sorted(set(re.findall(r"\(NEEDED\).*?\[(.*?)\]", output))),
                "dynamic_sections": output.count("Dynamic section at offset")}
    interpreters = [re.findall(r"Requesting program interpreter: ([^\]]+)", part)
                    for part in output.split("NODE_ELF\n", 1)]
    exported = any("__vsnprintf_chk" in line and " UND " not in line and "GLOBAL" in line for line in output.splitlines())
    if len(interpreters) != 2 or not exported:
        raise Failure("ELF inspection or gcompat dynamic symbol evidence absent")
    return {"opencode_interpreter": interpreters[0] or "no PT_INTERP",
            "node_interpreter": interpreters[1] or "no PT_INTERP",
            "gcompat_exports___vsnprintf_chk": exported}


def prepare_home(home, config, cold, plugins=PLUGINS):
    mounts = ["-v", home + ":" + HOME, "-v", config + ":" + CONFIG]
    helper(["--network=none", "--user=0:0", "--cap-add=CHOWN", *mounts],
           "chown -R 1000:1000 " + (HOME if cold else CONFIG))
    seed = "mkdir -p " + HOME + "/.cache " + HOME + "/.local/share/context-mode " + HOME + "/.local/state; "
    if cold:
        seed += "test ! -e " + HOME + "/.cache/opencode/packages; test ! -e " + HOME + "/.opencode-mem; "
    # stdin contains only synthetic config; no external installer or package scripts.
    seed += "IFS= read -r config; printf '%s\\n' \"$config\" > " + CONFIG + "/opencode.json; "
    seed += "IFS= read -r memory; printf '%s\\n' \"$memory\" > " + CONFIG + "/opencode-mem.jsonc"
    helper(["--network=none", "--user=1000:1000", *mounts], seed,
           data=json.dumps({**OPENCODE, "plugin": plugins}) + "\n" + json.dumps(MEMORY) + "\n")
    return mounts


def ready(name, arm):
    def config_ok(value):
        if not isinstance(value, dict):
            return False
        plugins = value.get("plugin")
        if not isinstance(plugins, list):
            raise Failure("malformed configured plugin list")
        specs = []
        for plugin in plugins:
            if isinstance(plugin, list):
                if len(plugin) != 2 or not isinstance(plugin[1], dict):
                    raise Failure("malformed configured plugin tuple")
                plugin = plugin[0]
            if not isinstance(plugin, str) or not plugin:
                raise Failure("malformed configured plugin spec")
            specs.append(plugin)
        if sorted(specs) != sorted(PLUGINS):
            raise Failure("configured plugin specs do not exactly match fixture")
        return value.get("enabled_providers") == [] and not value.get("mcp")
    wait(name, 4096, "/config", config_ok, window=420)
    ids = wait(name, 4096, "/experimental/tool/ids", lambda v: isinstance(v, list) and TOOLS.issubset(set(v)))
    if any(ids.count(tool) != 1 for tool in TOOLS):
        raise Failure("duplicate tool registration")
    wait(name, 4747, "/api/health", lambda v: isinstance(v, dict) and v.get("success") is True and v.get("status") == "ok")
    return json.loads(run(["exec", name, "node", "/probe/probe.mjs", arm]).stdout)


def recall(name, memory_id):
    payload = request(name, 4747, "/api/search?q=" + quote(SENTENCE) + "&tag=" + TAG + "&pageSize=20", timeout=180)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise Failure("real embedding recall failed")
    hits = [item for item in (payload.get("data") or {}).get("items", [])
            if item.get("type") == "memory" and item.get("id") == memory_id and item.get("content") == SENTENCE]
    similarity = hits[0].get("similarity") if hits else None
    if isinstance(similarity, bool) or not isinstance(similarity, (int, float)) or not math.isfinite(similarity) or similarity < 0.6:
        raise Failure("same id/content/finite similarity >=0.6 not recalled")
    return similarity


def arm_test(arm, runtime, inspect):
    global DEADLINE, CURRENT
    DEADLINE = time.monotonic() + 15 * 60
    CURRENT = {"status": "FAIL", "seconds": {}, "phase": "fresh HOME"}
    REPORT["arms"][arm] = CURRENT
    names = []
    home = None
    try:
        home = volume(arm + "-home")
        memory_id = None
        for lifecycle in ["cold", "warm"]:
            CURRENT["phase"] = lifecycle + " config preparation"
            config = volume(arm + "-config-" + lifecycle)
            mounts = prepare_home(home, config, lifecycle == "cold")
            name = PREFIX + "-" + arm + "-" + lifecycle
            names.append(name)
            CONTAINERS.append(name)
            CURRENT["phase"] = lifecycle + " bootstrap and host registration"
            start = time.monotonic()
            preload = ["-e", "LD_PRELOAD=" + ("/opt/runtime/lib/libgcompat.so.0" if arm == "B" else "")]
            run(["run", "-d", "--name", name, "--pull=never", "--platform=linux/amd64",
                 "--network=" + ("bridge" if lifecycle == "cold" else "none"), "--user=1000:1000",
                 *HARDEN, *ENV, *preload, *mounts, "-v", runtime + ":/opt/runtime:ro",
                 "-v", FIXTURES + ":/probe:ro", "-w", HOME,
                 IMAGE, "web", "--hostname", "127.0.0.1", "--port", "4096"])
            CURRENT[lifecycle + "_before_readiness"] = observe(name)
            CURRENT[lifecycle + "_probe"] = ready(name, arm)
            CURRENT["seconds"][lifecycle + "_bootstrap"] = round(time.monotonic() - start, 3)
            if lifecycle == "cold":
                CURRENT["phase"] = "first real embedding write"
                first = time.monotonic()
                payload = request(name, 4747, "/api/memories", {"content": SENTENCE, "containerTag": TAG}, timeout=300)
                CURRENT["seconds"]["first_write_attempt"] = round(time.monotonic() - first, 3)
                if not isinstance(payload, dict) or payload.get("success") is not True:
                    raise Failure("first real embedding write failed; no fallback")
                memory_id = (payload.get("data") or {}).get("id")
                if not isinstance(memory_id, str) or not memory_id:
                    raise Failure("memory write returned no id")
                CURRENT["seconds"]["first_write"] = round(time.monotonic() - first, 3)
                CURRENT["seconds"]["cold_to_write"] = round(time.monotonic() - start, 3)
            CURRENT["phase"] = lifecycle + " real embedding recall"
            first = time.monotonic()
            CURRENT[lifecycle + "_similarity"] = recall(name, memory_id)
            CURRENT["seconds"][lifecycle + "_recall"] = round(time.monotonic() - first, 3)
            CURRENT["same_memory_id"] = memory_id
            CURRENT["phase"] = lifecycle + " post-operation inspection"
            CURRENT[lifecycle + "_post_recall_probe"] = json.loads(
                run(["exec", name, "node", "/probe/probe.mjs", arm]).stdout)
            if arm == "B" and not CURRENT[lifecycle + "_post_recall_probe"]["host_gcompat_mapped"]:
                raise Failure("candidate gcompat absent from compiled host mappings after real embedding recall")
            CURRENT["onnx_elf"] = elf(runtime, inspect, home)
            if not CURRENT["onnx_elf"]["needed"]:
                raise Failure("ONNX DT_NEEDED evidence absent after real embedding recall")
            CURRENT[lifecycle + "_before_stop"] = observe(name)
            run(["stop", "--time=20", name], timeout=45)
            run(["rm", name])
            run(["volume", "rm", config])
            VOLUMES.remove(config)
        CURRENT["status"] = "PASS"
    except Exception as error:
        CURRENT["failure"] = str(error) if isinstance(error, Failure) else type(error).__name__
    finally:
        for name in names:
            CURRENT.setdefault("before_cleanup", []).append(observe(name))
            try:
                logs = run(["logs", "--tail=80", name], check=False, cleanup=True, timeout=10)
                CURRENT.setdefault("native_diagnostics", []).append(native_evidence(logs.stdout + logs.stderr))
                run(["rm", "-f", name], check=False, cleanup=True, timeout=20)
            except Failure:
                CURRENT["diagnostics_incomplete"] = True
        if home and "onnx_elf" not in CURRENT:
            try:
                CURRENT["onnx_elf"] = elf(runtime, inspect, home, cleanup=True)
            except Failure:
                CURRENT["onnx_elf_unavailable"] = True


def main():
    global DEADLINE
    try:
        started = time.monotonic()
        run(["pull", "--platform=linux/amd64", IMAGE], timeout=300)
        identity = run(["image", "inspect", "--format",
                        "{{json .RepoDigests}}|{{.Architecture}}|{{.Os}}|{{json .Config.Entrypoint}}", IMAGE]).stdout.strip().split("|")
        if len(identity) != 4 or identity[1:3] != ["amd64", "linux"] or json.loads(identity[3]) != ["opencode"]:
            raise Failure("stock image identity or entrypoint mismatch")
        if not any(item.endswith("@" + IMAGE.split("@")[1]) for item in json.loads(identity[0])):
            raise Failure("stock image digest mismatch")
        REPORT["image"] = IMAGE
        REPORT["pull_identity_seconds"] = round(time.monotonic() - started, 3)
        runtime, inspect = volume("runtime"), volume("inspect")
        started = time.monotonic()
        helper(["--network=bridge", "--user=0:0", "--cap-add=CHOWN",
                "-v", runtime + ":/opt/runtime", "-v", inspect + ":/opt/inspect",
                "-v", FIXTURES + ":/probe:ro"], "sh /probe/prepare.sh", timeout=300)
        REPORT["provision_seconds"] = round(time.monotonic() - started, 3)
        for label, root in [("runtime", runtime), ("inspect", inspect)]:
            output = helper(["--network=none", "--user=1000:1000", "-v", root + ":/opt/deps:ro"],
                            "apk --root /opt/deps list --installed --manifest").stdout
            packages = [line.split() for line in output.splitlines() if line.strip()]
            if not packages or any(len(p) != 2 or not all(re.fullmatch(r'[A-Za-z0-9_.+~-]+', s) for s in p) for p in packages):
                raise Failure("installed package manifest malformed")
            REPORT[label + "_packages"] = packages
            scripts = helper(["--network=none", "--user=0:0", "-v", root + ":/opt/deps:ro"],
                             "for f in /opt/deps/lib/apk/db/scripts.tar /opt/deps/lib/apk/db/scripts.tar.gz; "
                             "do if test -f \"$f\"; then tar -tf \"$f\"; fi; done").stdout.splitlines()
            if any(not re.fullmatch(r'[A-Za-z0-9_.+~/-]+', item) for item in scripts):
                raise Failure("unexpected package script inventory")
            REPORT[label + "_skipped_scripts"] = scripts[:100]
            REPORT[label + "_skipped_script_count"] = len(scripts)
        REPORT["elf"] = elf(runtime, inspect)
        # Independent budgets; the expected control failure cannot starve/skip B.
        arm_test("A", runtime, inspect)
        arm_test("B", runtime, inspect)
        run_cases(sys.modules[__name__], runtime)
    except Exception as error:
        REPORT["setup_failure"] = str(error) if isinstance(error, Failure) else type(error).__name__
    finally:
        cleanup_ok = True
        for kind, names in [("container", CONTAINERS), ("volume", VOLUMES)]:
            for name in reversed(names):
                try:
                    result = run([kind, "inspect", "--format", "{{.Name}}", name], check=False, cleanup=True, timeout=10)
                    if result.returncode:
                        # Distinguish absence from daemon failure without dumping inspect data.
                        missing = "no such" in result.stderr.lower()
                        cleanup_ok = cleanup_ok and missing
                        continue
                    run([kind, "rm", "-f", name], cleanup=True, timeout=20)
                except Failure:
                    cleanup_ok = False
        REPORT["cleanup_ok"] = cleanup_ok
        passed = cleanup_ok and "setup_failure" not in REPORT and REPORT["arms"].get("B", {}).get("status") == "PASS"
        REPORT["status"] = "PASS" if passed else "FAIL"
        output = json.dumps(REPORT, indent=2)
        print(output, flush=True)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf8") as summary:
                summary.write("## Init runtime feasibility\n\n```json\n" + output + "\n```\n")
    return 0 if passed else 1


def interrupted(_signum, _frame):
    raise Failure("interrupted")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    sys.exit(main())
