"""Short observational cases; never substitute for the required B gate."""

import json
import time


def run_cases(r, runtime):
    for label, plugins in [("no-configured-plugins", []),
                           ("context-only", [r.PLUGINS[0]]), ("mem-only", [r.PLUGINS[1]])]:
        started = time.monotonic()
        r.DEADLINE = started + 120
        case = {"plugins": plugins, "config_ready": False, "survived_window": False, "samples": []}
        r.REPORT.setdefault("diagnostic_cases", {})[label] = case
        r.CURRENT = case
        name = r.PREFIX + "-diagnostic-" + label
        try:
            home = r.volume("diagnostic-" + label + "-home")
            config = r.volume("diagnostic-" + label + "-config")
            mounts = r.prepare_home(home, config, True, plugins)
            r.CONTAINERS.append(name)
            r.run(["run", "-d", "--name", name, "--pull=never", "--platform=linux/amd64",
                   "--network=bridge", "--user=1000:1000", *r.HARDEN, *r.ENV,
                   "-e", "LD_PRELOAD=/opt/runtime/lib/libgcompat.so.0", *mounts,
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
                        if not all(isinstance(p, str) for p in specs) or sorted(specs) != sorted(plugins):
                            raise r.Failure("diagnostic plugin list mismatch")
                        if value.get("enabled_providers") != [] or value.get("mcp"):
                            raise r.Failure("diagnostic provider or MCP config mismatch")
                        case["config_ready"] = True
                        case["config_seconds"] = round(time.monotonic() - started, 3)
                time.sleep(2)
            final = r.observe(name)
            case["end_of_window"] = final
            case["survived_window"] = time.monotonic() >= r.DEADLINE - 10 and final.get("state", {}).get("Running") is True
        except Exception as error:
            case["failure"] = str(error) if isinstance(error, r.Failure) else type(error).__name__
        finally:
            case["before_cleanup"] = r.observe(name)
            case["observed_seconds"] = round(time.monotonic() - started, 3)
            try:
                logs = r.run(["logs", "--tail=80", name], timeout=10, check=False, cleanup=True)
                case["crash_evidence"] = r.native_evidence(logs.stdout + logs.stderr)
                r.run(["rm", "-f", name], timeout=20, check=False, cleanup=True)
            except r.Failure:
                case["diagnostics_incomplete"] = True
