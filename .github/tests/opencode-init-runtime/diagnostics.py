"""Bounded diagnostic-only cases; never substitute for the required B gate."""

import json
import re
import time


def evidence(r, name):
    logs = r.run(["logs", "--tail=80", name], timeout=10, check=False, cleanup=True)
    text = (logs.stdout + logs.stderr)[-65536:]
    result = r.native_evidence(text)
    lookups = re.findall(r"symbol [A-Za-z_][A-Za-z0-9_]* with version [A-Za-z0-9_.-]+ is being redirected|loading library [^\r\n]{1,200}? was requested in namespace -?\d+", text)
    result["gcompat_lookups"] = [r.sanitize(line)[:256] for line in lookups[-20:]]
    result["stages"] = []
    for line in logs.stdout.splitlines():
        if not line.startswith("NATIVE ") or len(result["stages"]) >= 40:
            continue
        try:
            item = json.loads(line[7:])
            # Only fixture-authored metadata, never arbitrary stdout/response data.
            clean = {}
            for key in ("stage", "mode", "node", "name", "version", "entry", "artifact", "error", "bytes", "inputs", "dimensions", "libraries"):
                if key not in item:
                    continue
                value = item[key]
                if key in ("entry", "artifact", "libraries"):
                    values = value if isinstance(value, list) else [value]
                    if not all(isinstance(v, str) and len(v) <= 512 and re.fullmatch(r"[A-Za-z0-9_@./+-]+", v) and not v.startswith(("/", "..")) for v in values):
                        continue
                    clean[key] = value
                elif isinstance(value, str):
                    clean[key] = r.sanitize(value)
                elif isinstance(value, int):
                    clean[key] = value
            result["stages"].append(clean)
        except (ValueError, TypeError):
            result["malformed_marker"] = True
    return result


def run_cases(r, runtime):
    overall = time.monotonic() + 360
    started = time.monotonic()
    r.DEADLINE = started + 120
    case = {"plugins": [r.PLUGINS[1]], "config_ready": False, "samples": []}
    r.REPORT["diagnostic_cases"] = {"mem-only-debug": case}
    r.CURRENT = case
    name = r.PREFIX + "-diagnostic-mem-debug"
    home = None
    try:
        home = r.volume("diagnostic-mem-debug-home")
        config = r.volume("diagnostic-mem-debug-config")
        mounts = r.prepare_home(home, config, True, [r.PLUGINS[1]])
        r.CONTAINERS.append(name)
        r.run(["run", "-d", "--name", name, "--pull=never", "--platform=linux/amd64",
               "--network=bridge", "--user=1000:1000", *r.HARDEN, *r.ENV,
               "-e", "LD_PRELOAD=/opt/runtime/lib/libgcompat.so.0", "-e", "GLIBC_FAKE_DEBUG=1", *mounts,
               "-v", runtime + ":/opt/runtime:ro", "-v", r.FIXTURES + ":/probe:ro",
               "-w", r.HOME, r.IMAGE, "web", "--hostname", "127.0.0.1", "--port", "4096"])
        next_sample = 0
        while time.monotonic() < r.DEADLINE - 10:
            elapsed = time.monotonic() - started
            if elapsed >= next_sample and len(case["samples"]) < 8:
                sample = r.observe(name)
                sample["elapsed_seconds"] = round(elapsed, 3)
                case["samples"].append(sample)
                next_sample = elapsed + 15
                if sample.get("state", {}).get("Running") is False:
                    break
            if not case["config_ready"]:
                value = r.request(name, 4096, "/config", timeout=5)
                if isinstance(value, dict):
                    specs = value.get("plugin")
                    if not isinstance(specs, list):
                        raise r.Failure("diagnostic malformed plugin list")
                    specs = [p[0] if isinstance(p, list) and len(p) == 2 and isinstance(p[1], dict) else p for p in specs]
                    if specs != [r.PLUGINS[1]] or value.get("enabled_providers") != [] or value.get("mcp"):
                        raise r.Failure("diagnostic config mismatch")
                    case["config_ready"] = True
                    case["config_seconds"] = round(time.monotonic() - started, 3)
            time.sleep(2)
    except Exception as error:
        case["failure"] = str(error) if isinstance(error, r.Failure) else type(error).__name__
    finally:
        case["before_cleanup"] = r.observe(name)
        case["observed_seconds"] = round(time.monotonic() - started, 3)
        try:
            case["evidence"] = evidence(r, name)
            r.run(["rm", "-f", name], timeout=20, check=False, cleanup=True)
        except r.Failure:
            case["diagnostics_incomplete"] = True
    if home is None:
        return
    # Separate Node processes, no network and read-only source HOME/cache. All
    # synthetic mutations (including SQLite CRUD) stay in each fresh /tmp.
    for mode in ("libsql", "sharp", "onnx", "transformers"):
        r.DEADLINE = min(overall, time.monotonic() + 45)
        name = r.PREFIX + "-native-" + mode
        result = {"runtime": "Node diagnostic, not OpenCode compatibility"}
        r.REPORT.setdefault("native_cases", {})[mode] = result
        r.CONTAINERS.append(name)
        try:
            r.run(["run", "-d", "--name", name, "--pull=never", "--platform=linux/amd64",
                   "--network=none", "--user=1000:1000", *r.HARDEN, *r.ENV,
                   "-e", "LD_PRELOAD=/opt/runtime/lib/libgcompat.so.0", "-e", "GLIBC_FAKE_DEBUG=1",
                   "-v", home + ":" + r.HOME + ":ro", "-v", runtime + ":/opt/runtime:ro",
                   "-v", r.FIXTURES + ":/probe:ro", "-w", "/tmp", "--entrypoint=node",
                   r.IMAGE, "/probe/native.mjs", mode])
            waited = r.run(["wait", name], timeout=45, check=False)
            result["wait_returncode"] = waited.returncode
        except r.Failure as error:
            result["failure"] = str(error)
        finally:
            result["before_cleanup"] = r.observe(name)
            try:
                result["evidence"] = evidence(r, name)
                r.run(["rm", "-f", name], timeout=20, check=False, cleanup=True)
            except r.Failure:
                result["diagnostics_incomplete"] = True
