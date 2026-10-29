#!/usr/bin/env python3
import base64, hashlib, io, json, os, re, signal, sqlite3, subprocess, sys, tarfile, tempfile, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
LOCAL_HTTP = urlreq.build_opener(urlreq.ProxyHandler({}))

IMAGE = "ghcr.io/anomalyco/opencode:1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8"
PLATFORM = "linux/amd64"
APP_PORT = 4096
PLUGIN_VERSION = "1.0.169"
TARBALL_URL = "https://registry.npmjs.org/context-mode/-/context-mode-1.0.169.tgz"
TARBALL_SHA512_B64 = "94JIaFuLjF9SO2BsGTrbGtyT44K95+9OC8BdbaL/UT76xOkanJLfUR5CzmNw+GELXZQqH4nBrKg9wjBnSFkVnQ=="
SELECTED_MEMBERS = ["package.json", "build/adapters/opencode/plugin.js", "build/db-base.js", "build/server.js", "hooks/security.bundle.mjs"]
MARKER = "quartzanchor9f31"
INDEX_SOURCE = "fixture-a"
DENY_SOURCE = "fixture-native-deny"
ASK_SOURCE = "fixture-native-ask"
BROKEN_SOURCE = "fixture-broken-security"
DIR_A = "/home/opencode/projects/a"
DIR_B = "/home/opencode/projects/b"
CACHE_ROOT = "/home/opencode/.cache/opencode"
TESTDIR = os.path.dirname(os.path.abspath(__file__))
RUN_ID = uuid.uuid4().hex[:12]
GLOBAL_BUDGET_S = 1500.0
START = time.monotonic()
TEST_ORDER = ["artifact_tarball", "baseline_network_probe", "registry_tools_and_package", "host_ctx_index", "host_ctx_search_same_session", "host_ctx_index_malformed", "restricted_deny", "ask_permission_gate", "plugin_policy_deny_ask", "project_isolation", "warm_persistence_and_sharing", "broken_security_fail_closed", "resume_isolation_gate", "cleanup"]
RESULTS = {name: {"status": "NOT_RUN", "detail": ""} for name in TEST_ORDER}
OBSERVATIONS = {"restricted_advertised": None, "ask_pending_observed": None, "asks_observed": 0, "reply_endpoint_verified": False, "content_store_shared_observed": None, "resume_marker_injection_observed": False, "aux_requests_served": 0, "error": None}
CREATED = {"containers": [], "volumes": [], "networks": []}
CURRENT = [None]
CLEANING = False
CLEANUP_DEADLINE = None
CASE_INPUTS = {}
RESUME_MARKER = "syntheticresume" + RUN_ID

class CiError(Exception):
    def __init__(self, scope):
        super().__init__(scope)
        self.scope = scope

def budget():
    if time.monotonic() - START > GLOBAL_BUDGET_S:
        raise CiError("TIMEOUT")

def finish(name, ok, detail=""):
    RESULTS[name]["status"] = "PASS" if ok else "FAIL"; RESULTS[name]["detail"] = detail

def record_error(scope, cls=None):
    OBSERVATIONS["error"] = {"scope": scope, "class": cls or scope, "current": CURRENT[0]}
    if CURRENT[0] and RESULTS[CURRENT[0]]["status"] == "NOT_RUN":
        RESULTS[CURRENT[0]]["status"] = "FAIL"; RESULTS[CURRENT[0]]["detail"] = "bootstrap_error"

def shq(value):
    return "'" + value.replace("'", "'\\''") + "'"

def dock(args, timeout=240, stdin=None):
    if CLEANING:
        remaining = CLEANUP_DEADLINE - time.monotonic()
        if remaining <= 0:
            raise CiError("CLEANUP_TIMEOUT")
        timeout = min(timeout, remaining)
    else:
        budget()
        timeout = min(timeout, max(1, GLOBAL_BUDGET_S - (time.monotonic() - START)))
    try:
        proc = subprocess.run(["docker", *args], capture_output=True, input=stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CiError("DOCKER_TIMEOUT")
    if proc.returncode != 0:
        raise CiError("DOCKER")
    return proc.stdout

def dock_rc(args, timeout=120):
    budget()
    proc = subprocess.run(["docker", *args], capture_output=True, timeout=min(timeout, max(1, GLOBAL_BUDGET_S - (time.monotonic() - START))))
    return proc.returncode

SIM_LOCK = threading.Lock()
SIM_PLANS = {}
SIM_CASE_OBS = {}
SIM_AUX = [0]

def register_plan(case, tool, args):
    with SIM_LOCK:
        SIM_PLANS[case] = {"tool": tool, "args": args, "stage": 0}
        SIM_CASE_OBS[case] = {"offered": set(), "marker_first": None, "emitted": None}
        CASE_INPUTS[case] = args

def case_obs(case):
    with SIM_LOCK:
        obs = SIM_CASE_OBS.get(case)
        if obs is None:
            return {"offered": set(), "marker_first": None, "emitted": None}
        return {"offered": set(obs["offered"]), "marker_first": obs["marker_first"], "emitted": obs["emitted"]}

def chunk(delta, finish_reason=None):
    return {"id": "chatcmpl-ci", "object": "chat.completion.chunk", "created": 0, "model": "probe", "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}

def sse_bytes(events):
    payload = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
    return payload + b"data: [DONE]\n\n"

class SimHandler(BaseHTTPRequestHandler):
    timeout = 65
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        return

    def _reply(self, code, body=b"", content_type="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, b"ok")
        else:
            self._reply(404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._reply(404)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._reply(400)
        if length <= 0 or length > 2000000:
            return self._reply(413)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except Exception:
            return self._reply(400)
        case = None
        marker_here = False
        messages = body.get("messages") if isinstance(body, dict) else None
        if isinstance(messages, list):
            marker_here = RESUME_MARKER in json.dumps([m for m in messages if isinstance(m, dict) and m.get("role") == "system"])
            for message in reversed(messages):
                if not isinstance(message, dict) or message.get("role") != "user":
                    continue
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, (str, list)):
                    found = re.search(r"CASE:([0-9a-f]{32})", json.dumps(content))
                    if found:
                        case = found.group(1); break
        offered = set()
        tools = body.get("tools") if isinstance(body, dict) else None
        if isinstance(tools, list):
            for tool in tools:
                try:
                    offered.add(tool["function"]["name"])
                except Exception:
                    pass
        with SIM_LOCK:
            plan = SIM_PLANS.get(case) if case else None
            if plan is None:
                SIM_AUX[0] += 1
                events = [chunk({"role": "assistant", "content": "DONE"}), chunk({}, "stop")]
            else:
                obs = SIM_CASE_OBS[case]
                obs["offered"] |= offered
                if obs["marker_first"] is None:
                    obs["marker_first"] = marker_here
                if plan["stage"] == 0:
                    plan["stage"] = 1
                    if plan["tool"] is None:
                        events = [chunk({"role": "assistant", "content": "DONE"}), chunk({}, "stop")]
                    else:
                        obs["emitted"] = plan["tool"]
                        call = {"index": 0, "id": "call_" + case, "type": "function", "function": {"name": plan["tool"], "arguments": json.dumps(plan["args"])}}
                        events = [chunk({"role": "assistant", "tool_calls": [call]}), chunk({}, "tool_calls")]
                else:
                    events = [chunk({"role": "assistant", "content": "DONE"}), chunk({}, "stop")]
            OBSERVATIONS["aux_requests_served"] = SIM_AUX[0]
        self._reply(200, sse_bytes(events), content_type="text/event-stream")

def start_sim(gateway_ip):
    server = ThreadingHTTPServer((gateway_ip, 0), SimHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]

def app_http(method, url, directory, payload=None, timeout=30):
    data = None
    headers = {"x-opencode-directory": directory}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urlreq.Request(url, data=data, headers=headers, method=method)
    try:
        with LOCAL_HTTP.open(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except HTTPError as exc:
        return exc.code, None
    except (URLError, OSError, ValueError):
        raise CiError("HTTP")

def net_create():
    name = "ctxprobe-net-" + RUN_ID
    CREATED["networks"].append(name)
    dock(["network", "create", "--internal", name], timeout=60)
    out = dock(["network", "inspect", "--format", "{{range .IPAM.Config}}{{.Gateway}} {{end}}", name]).decode()
    tokens = [t for t in out.split() if t]
    if not tokens:
        raise CiError("DOCKER")
    return name, tokens[0]

def ctr_networks(cid):
    out = dock(["inspect", "--format", "{{json .NetworkSettings.Networks}}", cid]).decode()
    networks = json.loads(out)
    if not isinstance(networks, dict) or not networks:
        raise CiError("DOCKER")
    return networks

def ctr_ip_on(cid, net):
    entry = ctr_networks(cid).get(net) or {}; ip = entry.get("IPAddress") or ""
    if not ip:
        raise CiError("DOCKER")
    return ip

def assert_only_net(cid, net):
    networks = ctr_networks(cid)
    if set(networks) != {net}:
        raise CiError("ASSERT")
    return ctr_ip_on(cid, net)

def vol_create(label):
    name = "ctxprobe-" + label + "-" + RUN_ID
    CREATED["volumes"].append(name)
    dock(["volume", "create", name], timeout=60)
    return name

SETTINGS_JSON = json.dumps({"permissions": {"deny": ["Bash(touch *deny-sentinel*)"], "ask": ["Bash(touch *ask-sentinel*)"]}})

def config_json(gateway, port):
    return {"$schema": "https://opencode.ai/config.json", "mcp": {}, "plugin": ["context-mode@" + PLUGIN_VERSION],
            "permission": {"*": "deny", "ctx_index": "allow", "ctx_search": "allow", "ctx_execute": "allow"}, "enabled_providers": ["fixture"],
            "model": "fixture/probe", "small_model": "fixture/probe", "default_agent": "probe",
            "agent": {"probe": {"mode": "primary", "steps": 3, "prompt": "CI probe agent."},
                      "other": {"mode": "primary", "steps": 3, "prompt": "CI other agent."},
                      "restricted": {"mode": "primary", "steps": 3, "prompt": "CI restricted agent.", "permission": {"*": "deny"}},
                      "ask": {"mode": "primary", "steps": 3, "prompt": "CI ask agent.", "permission": {"*": "deny", "ctx_index": "ask"}}},
            "share": "disabled", "autoupdate": False,
            "provider": {"fixture": {"npm": "@ai-sdk/openai-compatible",
                                     "options": {"baseURL": "http://%s:%d/v1" % (gateway, port), "apiKey": "ci-synthetic-not-secret"},
                                     "models": {"probe": {"name": "probe", "tool_call": True, "limit": {"context": 128000, "output": 1024}, "cost": {"input": 0, "output": 0}}}}}}

def seed_volumes(home_vol, cfg_vol, config):
    name = "ctxprobe-seed-" + uuid.uuid4().hex
    CREATED["containers"].append(name)
    mounts = ["-v", home_vol + ":/home/opencode", "-v", cfg_vol + ":/home/opencode/.config/opencode"]
    dock(["run", "--name", name, "--platform", PLATFORM, "--network", "none", "--user", "0:0", "--read-only", "--cap-drop", "ALL", "--cap-add", "CHOWN", "--security-opt", "no-new-privileges", *mounts, "--entrypoint", "/bin/sh", IMAGE, "-ec", "chown 1000:1000 /home/opencode /home/opencode/.config/opencode"], timeout=60)
    dock(["rm", name]); CREATED["containers"].remove(name)
    name = "ctxprobe-seed-" + uuid.uuid4().hex
    CREATED["containers"].append(name)
    script = ("mkdir -p /home/opencode/projects/a/.claude /home/opencode/projects/b; "
              "printf '%s' " + shq(SETTINGS_JSON) + " > /home/opencode/projects/a/.claude/settings.json; "
              "IFS= read -r config; printf '%s\\n' \"$config\" > /home/opencode/.config/opencode/opencode.json")
    dock(["run", "--name", name, "-i", "--platform", PLATFORM, "--network", "none", "--user", "1000:1000", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", *mounts, "--entrypoint", "/bin/sh", IMAGE, "-ec", script], timeout=60, stdin=(json.dumps(config) + "\n").encode())
    dock(["rm", name]); CREATED["containers"].remove(name)

def app_create(net, home_vol, cfg_vol, extra_env=None):
    name = "ctxprobe-app-" + uuid.uuid4().hex
    CREATED["containers"].append(name)
    args = ["create", "--name", name, "--platform", PLATFORM, "--user", "1000:1000", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory=1g", "--cpus=2",
            "--ulimit", "core=0", "--tmpfs", "/tmp:rw,size=256m,mode=1777", "--network", net, "-v", home_vol + ":/home/opencode",
            "-v", cfg_vol + ":/home/opencode/.config/opencode", "-v", TESTDIR + ":/probe:ro",
            "-e", "HOME=/home/opencode", "-e", "XDG_CONFIG_HOME=/home/opencode/.config", "-e", "XDG_DATA_HOME=/home/opencode/.local/share",
            "-e", "XDG_STATE_HOME=/home/opencode/.local/state", "-e", "XDG_CACHE_HOME=/home/opencode/.cache", "-e", "XDG_BIN_HOME=/home/opencode/.local/bin",
            "-e", "CONTEXT_MODE_DIR=/home/opencode/.local/share/context-mode", "-e", "CONTEXT_MODE_DATA_DIR=/home/opencode/.local/share", "-e", "CONTEXT_MODE_REQUIRE_SECURITY=1"]
    for key, value in (extra_env or {}).items():
        args += ["-e", key + "=" + value]
    args += ["-w", DIR_A, IMAGE, "web", "--hostname", "0.0.0.0", "--port", str(APP_PORT)]
    dock(args, timeout=60)
    return name

def wait_ready(app, deadline_s=300):
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        budget()
        try:
            status, _ = app_http("GET", app + "/config", DIR_A, timeout=10)
            if status == 200:
                status2, ids = app_http("GET", app + "/experimental/tool/ids", DIR_A, timeout=10)
                if status2 == 200 and isinstance(ids, list) and "ctx_index" in ids and "ctx_search" in ids:
                    return True
        except CiError:
            pass
        time.sleep(2)
    return False

def new_session(app, directory, title):
    status, body = app_http("POST", app + "/session", directory, {"title": title})
    if status != 200 or not isinstance(body, dict) or not body.get("id"):
        raise CiError("HTTP")
    if body.get("directory") != directory:
        raise CiError("SESSION_DIRECTORY")
    return body["id"]

def dispatch(app, directory, session_id, case, agent, extra_text=""):
    payload = {"model": {"providerID": "fixture", "modelID": "probe"}, "agent": agent, "parts": [{"type": "text", "text": "CASE:" + case + " " + extra_text}]}
    status, _ = app_http("POST", app + "/session/" + session_id + "/prompt_async", directory, payload)
    if status not in (200, 202, 204):
        raise CiError("HTTP")

def fetch_messages(app, directory, session_id):
    status, body = app_http("GET", app + "/session/" + session_id + "/message", directory)
    if status != 200:
        raise CiError("HTTP")
    if isinstance(body, dict):
        body = body.get("messages") or ([body] if body.get("parts") else [])
    return body if isinstance(body, list) else []

def find_tool_part(messages_list, name, case, allow_invalid=False):
    for message in messages_list:
        if not isinstance(message, dict):
            continue
        for part in message.get("parts") or []:
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            tool_id = str(part.get("tool") or "")
            if part.get("callID") == "call_" + case and (tool_id == name or (allow_invalid and tool_id == "invalid")):
                state = part.get("state") or {}
                if state.get("status") in ("completed", "error"):
                    return part
    return None

def wait_tool(app, directory, session_id, name, case, timeout_s=90, allow_invalid=False):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        budget()
        part = find_tool_part(fetch_messages(app, directory, session_id), name, case, allow_invalid)
        if part:
            return part
        time.sleep(1)
    return None

def status_of(part):
    return ((part or {}).get("state") or {}).get("status") or ""

def tool_text(part):
    state = (part or {}).get("state") or {}
    return " ".join(str(p) for p in (state.get("output"), state.get("error")) if p)

def status_detail(part):
    if not part:
        return "no_tool_result"
    return "tool_" + (status_of(part) or "unknown")

def abort_session(app, directory, session_id):
    status, result = app_http("POST", app + "/session/" + session_id + "/abort", directory, {})
    if status != 200 or result is not True:
        raise CiError("ABORT_FAILED")
    await_idle(app, directory, session_id)

def await_idle(app, directory, session_id):
    for _ in range(60):
        budget()
        status, states = app_http("GET", app + "/session/status", directory)
        if status == 200 and isinstance(states, dict) and states.get(session_id, {}).get("type", "idle") == "idle":
            return
        time.sleep(1)
    raise CiError("SESSION_TIMEOUT")

def expected_input(part, case):
    return isinstance(part, dict) and (part.get("state") or {}).get("input") == CASE_INPUTS[case]

def hidden_tool_rejected(part, case, name, observed):
    if not isinstance(part, dict) or part.get("callID") != "call_" + case or part.get("tool") != "invalid":
        return False
    if observed["emitted"] != name or name in observed["offered"] or status_of(part) not in ("completed", "error"):
        return False
    args = (part.get("state") or {}).get("input")
    if not isinstance(args, dict) or args.get("tool") != name or not isinstance(args.get("error"), str):
        return False
    return any(phrase in args["error"].lower() for phrase in ("unavailable tool", "unknown tool", "no such tool", "not available", "not found", "not allowed"))

def context_db_locations(cid, kind, directory):
    name = hashlib.sha256(directory.encode()).hexdigest()[:16] + ".db"
    roots = {"persistent": "/home/opencode/.local/share/context-mode/", "ephemeral": "/home/opencode/.config/opencode/context-mode/"}
    found = {}
    for label, root in roots.items():
        rc = dock_rc(["exec", cid, "/bin/sh", "-c", "test -f " + shq(root + kind + "/" + name)], timeout=10)
        if rc not in (0, 1):
            raise CiError("DB_LOCATION")
        found[label] = rc == 0
    return found

def inspect_synthetic_db(cid, kind, directory, inspect):
    db_name = hashlib.sha256(directory.encode()).hexdigest()[:16] + ".db"
    root = "/home/opencode/.local/share/context-mode/" + kind
    with tempfile.TemporaryDirectory(prefix="ctxprobe-db-") as temp:
        for suffix in ("", "-wal", "-shm"):
            name = db_name + suffix
            remote = root + "/" + name
            if suffix:
                rc = dock_rc(["exec", cid, "/bin/sh", "-c", "test -f " + shq(remote)], timeout=10)
                if rc == 1:
                    continue
                if rc != 0:
                    raise CiError("DB_SNAPSHOT")
            payload = dock(["cp", cid + ":" + remote, "-"], timeout=15)
            if len(payload) > 4 * 1024 * 1024:
                raise CiError("DB_SNAPSHOT")
            with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
                members = archive.getmembers()
                if len(members) != 1 or not members[0].isfile() or members[0].size > 3 * 1024 * 1024:
                    raise CiError("DB_SNAPSHOT")
                with open(os.path.join(temp, name), "wb") as output:
                    output.write(archive.extractfile(members[0]).read())
        with sqlite3.connect("file:" + os.path.join(temp, db_name) + "?mode=ro", uri=True) as db:
            return inspect(db)

def indexed_marker_present(cid, marker):
    def inspect(db):
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            if not re.fullmatch(r"[A-Za-z0-9_]+", table):
                raise CiError("DB_SCHEMA")
            rows = db.execute('SELECT * FROM "' + table + '" LIMIT 1001').fetchall()
            if len(rows) > 1000:
                raise CiError("DB_BUDGET")
            if any(marker in str(value) for row in rows for value in row if isinstance(value, str)):
                return True
        return False
    try:
        locations = context_db_locations(cid, "content", DIR_A)
        OBSERVATIONS["content_db_locations"] = locations
        if not locations["persistent"]:
            return None
        return inspect_synthetic_db(cid, "content", DIR_A, inspect)
    except (CiError, sqlite3.Error, tarfile.TarError, OSError):
        OBSERVATIONS["content_db_inspection"] = "unavailable"
        return None

def recall_hit(part):
    return status_of(part) == "completed" and MARKER in tool_text(part) and INDEX_SOURCE in tool_text(part)

def read_content_presence(db, label, marker):
    row = db.execute("""SELECT
        EXISTS(SELECT 1 FROM sources WHERE label = :label),
        EXISTS(SELECT 1 FROM chunks c JOIN sources s ON s.id = c.source_id
               WHERE s.label = :label AND instr(c.content, :marker) > 0),
        EXISTS(SELECT 1 FROM chunks_trigram c JOIN sources s ON s.id = c.source_id
               WHERE s.label = :label AND instr(c.content, :marker) > 0)
        """, {"label": label, "marker": marker}).fetchone()
    return dict(zip(("source_present", "porter_marker", "trigram_marker"), map(bool, row)))

def observe_content_presence(cid):
    try:
        return inspect_synthetic_db(cid, "content", DIR_A, lambda db: read_content_presence(db, INDEX_SOURCE, MARKER))
    except (CiError, sqlite3.Error, tarfile.TarError, OSError):
        return None

def failure_markers(cid):
    try:
        result = subprocess.run(["docker", "logs", "--tail=40", cid], capture_output=True, timeout=10)
        raw = (result.stdout + result.stderr).decode(errors="replace").lower()
        known = ("node: not found", "permission denied", "read-only file system", "failed to load plugin", "failed to install plugin", "npminstallfailederror", "plugin export is not a function", "invalid config", "no such module: fts5")
        return [phrase for phrase in known if phrase in raw]
    except (subprocess.TimeoutExpired, OSError):
        return ["diagnostics_unavailable"]

def resume_case(app, cid):
    CURRENT[0] = "resume_isolation_gate"
    session_id = new_session(app, DIR_A, "ci-resume-source")
    status, _ = app_http("POST", app + "/session/" + session_id + "/message", DIR_A,
                         {"model": {"providerID": "fixture", "modelID": "probe"}, "agent": "probe", "noReply": True,
                          "parts": [{"type": "text", "text": "Synthetic continuity decision: retain " + RESUME_MARKER}]})
    if status != 200:
        raise CiError("RESUME_SETUP")
    status, body = app_http("POST", app + "/session/" + session_id + "/summarize", DIR_A,
                            {"providerID": "fixture", "modelID": "probe", "auto": False}, timeout=90)
    if status != 200 or body is not True:
        raise CiError("RESUME_SETUP")
    await_idle(app, DIR_A, session_id)
    locations = context_db_locations(cid, "sessions", DIR_A)
    OBSERVATIONS["session_db_locations"] = locations
    if not locations["persistent"]:
        finish("resume_isolation_gate", False, "persistent_context_db_unavailable")
        return
    seeded = inspect_synthetic_db(cid, "sessions", DIR_A,
        lambda db: any(RESUME_MARKER in str(row[0]) for row in db.execute(
            "SELECT snapshot FROM session_resume WHERE session_id=? AND consumed=0", (session_id,))))
    OBSERVATIONS["resume_snapshot_seeded"] = seeded
    if not seeded:
        finish("resume_isolation_gate", False, "snapshot_marker_not_seeded")
        return
    case = uuid.uuid4().hex
    register_plan(case, None, {})
    other = new_session(app, DIR_A, "ci-resume-other-agent")
    dispatch(app, DIR_A, other, case, "other")
    deadline = time.monotonic() + 60
    while case_obs(case)["marker_first"] is None and time.monotonic() < deadline:
        budget(); time.sleep(1)
    observed = case_obs(case)["marker_first"]
    await_idle(app, DIR_A, other)
    OBSERVATIONS["resume_marker_injection_observed"] = observed
    finish("resume_isolation_gate", observed is False,
           "cross_agent_resume_injection" if observed is True else "isolated" if observed is False else "no_host_request")

def verify_tarball():
    try:
        with urlreq.urlopen(urlreq.Request(TARBALL_URL), timeout=60) as resp:
            data = resp.read(8 * 1024 * 1024 + 1)
    except (URLError, OSError):
        raise CiError("HTTP")
    if not data or len(data) > 8 * 1024 * 1024:
        raise CiError("ASSERT")
    if base64.b64encode(hashlib.sha512(data).digest()).decode() != TARBALL_SHA512_B64:
        raise CiError("ASSERT")
    expected = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            manifest = json.load(tf.extractfile("package/package.json"))
            if manifest.get("version") != PLUGIN_VERSION:
                raise CiError("ASSERT")
            for rel in SELECTED_MEMBERS:
                expected[rel] = hashlib.sha256(tf.extractfile(tf.getmember("package/" + rel)).read()).hexdigest()
    except CiError:
        raise
    except Exception:
        raise CiError("ASSERT")
    return expected

def package_check(home_vol, cid, expected):
    pkg_dir = CACHE_ROOT + "/packages/context-mode@" + PLUGIN_VERSION + "/node_modules/context-mode"
    tar_bytes = dock(["cp", "-L", cid + ":" + pkg_dir, "-"], timeout=240)
    if len(tar_bytes) > 32 * 1024 * 1024:
        raise CiError("ASSERT")
    try:
        actual = installed_package_hashes(tar_bytes)
        for rel, want in expected.items():
            if actual[rel] != want:
                OBSERVATIONS["package_mismatch_member"] = rel
                raise CiError("PACKAGE_HASH_MISMATCH")
    except CiError:
        raise
    except Exception:
        raise CiError("ASSERT")

def installed_package_hashes(payload):
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
        members = {member.name.removeprefix("./"): member for member in archive.getmembers()}
        base = "context-mode/"
        manifest_member = members.get(base + "package.json")
        if manifest_member is None or not manifest_member.isfile():
            raise CiError("PACKAGE_MANIFEST_MISSING")
        manifest = json.load(archive.extractfile(manifest_member))
        if manifest.get("name") != "context-mode" or manifest.get("version") != PLUGIN_VERSION:
            raise CiError("PACKAGE_IDENTITY")
        hashes = {}
        for rel in SELECTED_MEMBERS:
            member = members.get(base + rel)
            if member is None or not member.isfile():
                raise CiError("PACKAGE_FILE_MISSING")
            hashes[rel] = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
        return hashes

def approval_outcome(pending, before, after, offered, indexed, case):
    for part in (before, after):
        if status_of(part) == "completed":
            return False, "bypass_completed" if expected_input(part, case) else "call_input_mismatch"
    if pending and offered:
        return (True, "pending_observed_rejected_via_abort") if indexed is False else (False, "absence_unverified")
    if status_of(before) == "error" or status_of(after) == "error":
        return False, "terminal_error_without_approval"
    return False, "no_pending_evidence"

def baseline_probe(net, gateway, port):
    def probe(network, script):
        name = "ctxprobe-network-" + uuid.uuid4().hex
        CREATED["containers"].append(name)
        rc = dock_rc(["run", "--name", name, "--platform", PLATFORM, "--network", network, "--user", "1000:1000", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", IMAGE, "-ec", script], timeout=30)
        dock(["rm", "-f", name]); CREATED["containers"].remove(name)
        return rc
    external = "command -v wget >/dev/null; wget -T 10 -q -O /dev/null https://registry.npmjs.org/context-mode/1.0.169"
    if probe("bridge", external) != 0:
        return False, "external_control_failed"
    cmd = "command -v wget >/dev/null; wget -T 3 -q -O /dev/null http://%s:%d/health || exit 3; " % (gateway, port)
    cmd += "wget -T 5 -q -O /dev/null https://registry.npmjs.org/context-mode/1.0.169 && exit 4; exit 0"
    rc = probe(net, cmd)
    if rc == 0:
        return True, "internal_health_ok_external_blocked"
    if rc == 3:
        return False, "internal_health_unreachable"
    if rc == 4:
        return False, "external_egress_unexpectedly_open"
    return False, "probe_container_error"

def sentinels_absent(cid):
    rc = dock_rc(["exec", cid, "/bin/sh", "-c",
                  "test ! -e /home/opencode/projects/a/deny-sentinel && test ! -e /home/opencode/projects/a/ask-sentinel"], timeout=90)
    return rc == 0

def policy_case(app, code, expected_phrase):
    case = uuid.uuid4().hex
    register_plan(case, "ctx_execute", {"language": "shell", "code": code})
    session_id = new_session(app, DIR_A, "ci-case-7")
    dispatch(app, DIR_A, session_id, case, "probe")
    part = wait_tool(app, DIR_A, session_id, "ctx_execute", case)
    abort_session(app, DIR_A, session_id)
    if not part or not expected_input(part, case) or "ctx_execute" not in case_obs(case)["offered"]:
        return False, "no_tool_result"
    if status_of(part) != "error":
        return False, "unexpected_completed"
    if expected_phrase not in tool_text(part):
        return False, "missing_expected_policy_error"
    return True, "policy_blocked"

def run_cold_cases(app, home, cid, expected):
    CURRENT[0] = "registry_tools_and_package"
    status, ids = app_http("GET", app + "/experimental/tool/ids", DIR_A)
    ok_ids = (status == 200 and isinstance(ids, list) and ids.count("ctx_index") == 1 and ids.count("ctx_search") == 1 and not any("memory" in str(i).lower() for i in ids))
    status2, tools = app_http("GET", app + "/experimental/tool?provider=fixture&model=probe", DIR_A)
    blob = json.dumps(tools)
    ok_tools = status2 == 200 and all(n in blob for n in ("ctx_index", "ctx_search", "ctx_execute"))
    try:
        package_check(home, cid, expected)
        ok_pkg = True
    except CiError as error:
        ok_pkg = False
        OBSERVATIONS["package_failure"] = error.scope
    finish("registry_tools_and_package", ok_ids and ok_tools and ok_pkg, "ids=%s schemas=%s package=%s" % (ok_ids, ok_tools, ok_pkg))
    budget()
    CURRENT[0] = "host_ctx_index"
    session2 = new_session(app, DIR_A, "ci-case-2")
    case2 = uuid.uuid4().hex
    register_plan(case2, "ctx_index", {"content": "# Synthetic\n" + MARKER + " retained proof", "source": INDEX_SOURCE})
    dispatch(app, DIR_A, session2, case2, "probe")
    part2 = wait_tool(app, DIR_A, session2, "ctx_index", case2)
    await_idle(app, DIR_A, session2)
    finish("host_ctx_index", expected_input(part2, case2) and status_of(part2) == "completed" and "Indexed" in tool_text(part2), status_detail(part2))
    budget()
    CURRENT[0] = "host_ctx_search_same_session"
    case3 = uuid.uuid4().hex
    register_plan(case3, "ctx_search", {"queries": [MARKER], "limit": 3})
    dispatch(app, DIR_A, session2, case3, "probe")
    part3 = wait_tool(app, DIR_A, session2, "ctx_search", case3)
    await_idle(app, DIR_A, session2)
    finish("host_ctx_search_same_session", expected_input(part3, case3) and recall_hit(part3), status_detail(part3))
    budget()
    CURRENT[0] = "host_ctx_index_malformed"
    session4 = new_session(app, DIR_A, "ci-case-4")
    case4 = uuid.uuid4().hex
    register_plan(case4, "ctx_index", {"content": 42})
    dispatch(app, DIR_A, session4, case4, "probe")
    part4 = wait_tool(app, DIR_A, session4, "ctx_index", case4)
    text4 = tool_text(part4).lower()
    finish("host_ctx_index_malformed", expected_input(part4, case4) and status_of(part4) == "error" and "content" in text4 and any(t in text4 for t in ("schema", "zod", "invalid")), status_detail(part4))
    budget()
    CURRENT[0] = "restricted_deny"
    session5 = new_session(app, DIR_A, "ci-case-5")
    case5 = uuid.uuid4().hex
    register_plan(case5, "ctx_index", {"content": "forbidden-marker-5-" + case5[:8], "source": DENY_SOURCE})
    dispatch(app, DIR_A, session5, case5, "restricted")
    part5 = wait_tool(app, DIR_A, session5, "ctx_index", case5, 60, allow_invalid=True)
    abort_session(app, DIR_A, session5)
    observed5 = case_obs(case5)
    OBSERVATIONS["restricted_advertised"] = "ctx_index" in case_obs(case5)["offered"]
    OBSERVATIONS["restricted_route"] = "invalid_repair" if part5 and part5.get("tool") == "invalid" else "target" if part5 else "none"
    OBSERVATIONS["restricted_terminal"] = status_of(part5) or None
    error5 = ((part5 or {}).get("state") or {}).get("error", "")
    OBSERVATIONS["restricted_input_matched"] = expected_input(part5, case5)
    OBSERVATIONS["restricted_error_markers"] = [word for word in ("permission", "denied", "unavailable", "unknown tool", "not found", "invalid") if word in str(error5).lower()]
    if part5 and part5.get("tool") == "ctx_index" and status_of(part5) == "completed":
        finish("restricted_deny", False, "observed_bypass_completed")
    elif RESULTS["registry_tools_and_package"]["status"] != "PASS":
        finish("restricted_deny", False, "blocked_by_artifact_check")
    elif RESULTS["host_ctx_index"]["status"] == "PASS" and expected_input(part5, case5) and status_of(part5) == "error" and any(p in tool_text(part5).lower() for p in ("denied", "permission", "not allowed")) and indexed_marker_present(cid, CASE_INPUTS[case5]["content"]) is False:
        finish("restricted_deny", True, "denied_error_observed")
    elif RESULTS["host_ctx_index"]["status"] == "PASS" and hidden_tool_rejected(part5, case5, "ctx_index", observed5) and indexed_marker_present(cid, CASE_INPUTS[case5]["content"]) is False:
        finish("restricted_deny", True, "hidden_tool_rejected_without_side_effect")
    else:
        finish("restricted_deny", False, "no_terminal_evidence")
    budget()
    CURRENT[0] = "ask_permission_gate"
    session6 = new_session(app, DIR_A, "ci-case-6")
    case6 = uuid.uuid4().hex
    register_plan(case6, "ctx_index", {"content": "ask-gate-proof", "source": ASK_SOURCE})
    dispatch(app, DIR_A, session6, case6, "ask")
    pending = False
    bypass = False
    part6 = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        budget()
        status, perms = app_http("GET", app + "/permission", DIR_A)
        items = perms if isinstance(perms, list) else ((perms or {}).get("permissions") if isinstance(perms, dict) else None)
        items = [p for p in items or [] if isinstance(p, dict) and p.get("sessionID") == session6 and p.get("permission") == "ctx_index" and (p.get("tool") or {}).get("callID") == "call_" + case6]
        part6 = find_tool_part(fetch_messages(app, DIR_A, session6), "ctx_index", case6)
        if status == 200 and items and part6 is None:
            pending = True
            OBSERVATIONS["ask_pending_observed"] = True
            OBSERVATIONS["asks_observed"] = len(items)
            break
        if part6 is not None:
            bypass = True
            break
        time.sleep(1)
    abort_session(app, DIR_A, session6)
    after_abort = find_tool_part(fetch_messages(app, DIR_A, session6), "ctx_index", case6)
    indexed = indexed_marker_present(cid, "ask-gate-proof")
    OBSERVATIONS["ask_terminal_before_abort"] = status_of(part6) or None
    OBSERVATIONS["ask_terminal_after_abort"] = status_of(after_abort) or None
    OBSERVATIONS["ask_input_matched"] = expected_input(after_abort or part6, case6)
    OBSERVATIONS["ask_indexed_after_abort"] = indexed
    ok, detail = approval_outcome(pending, part6, after_abort, "ctx_index" in case_obs(case6)["offered"], indexed, case6)
    finish("ask_permission_gate", ok, detail)
    budget()
    CURRENT[0] = "plugin_policy_deny_ask"
    control = uuid.uuid4().hex
    register_plan(control, "ctx_execute", {"language": "shell", "code": "printf 'policy-control-ok'"})
    control_session = new_session(app, DIR_A, "ci-policy-control")
    dispatch(app, DIR_A, control_session, control, "probe")
    control_part = wait_tool(app, DIR_A, control_session, "ctx_execute", control)
    await_idle(app, DIR_A, control_session)
    control_ok = expected_input(control_part, control) and status_of(control_part) == "completed" and "policy-control-ok" in tool_text(control_part) and "ctx_execute" in case_obs(control)["offered"]
    ok_deny, detail_deny = policy_case(app, "touch deny-sentinel", "security policy")
    ok_ask, detail_ask = policy_case(app, "touch ask-sentinel", "Blocked by context-mode")
    absent = sentinels_absent(cid)
    finish("plugin_policy_deny_ask", control_ok and ok_deny and ok_ask and absent, "control=%s deny=%s ask=%s sentinels_absent=%s" % (control_ok, detail_deny, detail_ask, absent))
    budget()
    CURRENT[0] = "project_isolation"
    session8 = new_session(app, DIR_B, "ci-case-8")
    case8 = uuid.uuid4().hex
    register_plan(case8, "ctx_search", {"queries": [MARKER], "limit": 3})
    dispatch(app, DIR_B, session8, case8, "probe")
    part8 = wait_tool(app, DIR_B, session8, "ctx_search", case8)
    if expected_input(part8, case8) and status_of(part8) == "completed":
        leak = INDEX_SOURCE in tool_text(part8)
        OBSERVATIONS["project_positive_source_seen"] = leak
        OBSERVATIONS["project_positive_content_seen"] = leak and "retained proof" in tool_text(part8)
        finish("project_isolation", not leak, "cross_project_leak" if leak else "no_cross_project_hit")
    else:
        finish("project_isolation", False, status_detail(part8))
    try:
        resume_case(app, cid)
    except (CiError, sqlite3.Error, tarfile.TarError, OSError) as error:
        finish("resume_isolation_gate", False, "setup_" + (error.scope if isinstance(error, CiError) else type(error).__name__))
    OBSERVATIONS["cold_positive_content"] = observe_content_presence(cid)
    return session2

def run_warm_cases(app, retained_session, cid):
    OBSERVATIONS["warm_positive_content_before_search"] = observe_content_presence(cid)
    case_a = uuid.uuid4().hex
    session_a = retained_session
    register_plan(case_a, "ctx_search", {"queries": [MARKER], "limit": 3})
    dispatch(app, DIR_A, session_a, case_a, "probe")
    part_a = wait_tool(app, DIR_A, session_a, "ctx_search", case_a)
    await_idle(app, DIR_A, session_a)
    ok_retained = expected_input(part_a, case_a) and recall_hit(part_a)
    case_b = uuid.uuid4().hex
    session_b = new_session(app, DIR_A, "ci-case-9b")
    register_plan(case_b, "ctx_search", {"queries": [MARKER], "limit": 3})
    dispatch(app, DIR_A, session_b, case_b, "other")
    part_b = wait_tool(app, DIR_A, session_b, "ctx_search", case_b)
    await_idle(app, DIR_A, session_b)
    ok_other = expected_input(part_b, case_b) and status_of(part_b) == "completed"
    shared = bool(part_b) and INDEX_SOURCE in tool_text(part_b) and MARKER in tool_text(part_b)
    OBSERVATIONS["content_store_shared_observed"] = shared
    injected = bool(case_obs(case_b)["marker_first"])
    finish("warm_persistence_and_sharing", ok_retained and ok_other and not injected, "retained=%s other_completed=%s shared=%s injected=%s" % (ok_retained, ok_other, shared, injected))

def run_broken_case(app):
    status, ids = app_http("GET", app + "/experimental/tool/ids", DIR_A)
    registry_ok = status == 200 and isinstance(ids, list) and "ctx_index" in ids
    session10 = new_session(app, DIR_A, "ci-case-10")
    case10 = uuid.uuid4().hex
    register_plan(case10, "ctx_index", {"content": "broken-bundle-proof", "source": BROKEN_SOURCE})
    dispatch(app, DIR_A, session10, case10, "probe")
    part10 = wait_tool(app, DIR_A, session10, "ctx_index", case10)
    fail_closed = expected_input(part10, case10) and status_of(part10) == "error" and "fail-closed engaged" in tool_text(part10)
    finish("broken_security_fail_closed", registry_ok and fail_closed, "registry=%s fail_closed=%s %s" % (registry_ok, fail_closed, status_detail(part10)))

def cleanup():
    global CLEANING, CLEANUP_DEADLINE
    CLEANING = True
    CLEANUP_DEADLINE = min(START + GLOBAL_BUDGET_S + 180, time.monotonic() + 180)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    ok = True
    for cid in list(CREATED["containers"]):
        try:
            dock(["rm", "-f", cid], timeout=90); CREATED["containers"].remove(cid)
        except CiError:
            ok = False
    for vol in list(CREATED["volumes"]):
        try:
            dock(["volume", "rm", vol], timeout=60); CREATED["volumes"].remove(vol)
        except CiError:
            ok = False
    for net in list(CREATED["networks"]):
        try:
            dock(["network", "rm", net], timeout=60); CREATED["networks"].remove(net)
        except CiError:
            ok = False
    return ok

def summarize():
    counts = {"PASS": 0, "FAIL": 0, "NOT_RUN": 0}
    for entry in RESULTS.values():
        counts[entry["status"]] += 1
    overall = "PASS" if counts["FAIL"] == 0 and counts["NOT_RUN"] == 0 else "FAIL"
    blocker = "required_gate_not_run" if counts["NOT_RUN"] else None
    report = {"overall": overall, "blocker": blocker, "counts": counts, "elapsed_s": round(time.monotonic() - START, 1), "run_id": RUN_ID, "tests": RESULTS, "observations": OBSERVATIONS}
    print(json.dumps(report, indent=2))
    return 0 if overall == "PASS" else 1

def run():
    server = None
    try:
        CURRENT[0] = "artifact_tarball"
        budget()
        expected = verify_tarball()
        finish("artifact_tarball", True, "sha512_and_selected_digests_verified")
        dock(["pull", "--platform", PLATFORM, IMAGE], timeout=600)
        net, gateway = net_create()
        server, sim_port = start_sim(gateway)
        ok, detail = baseline_probe(net, gateway, sim_port)
        finish("baseline_network_probe", ok, detail)
        budget()
        home = vol_create("home")
        cfg_cold = vol_create("cfg-cold")
        seed_volumes(home, cfg_cold, config_json(gateway, sim_port))
        cid = app_create(net, home, cfg_cold)
        dock(["network", "connect", "bridge", cid], timeout=60)
        dock(["start", cid], timeout=180)
        CURRENT[0] = "registry_tools_and_package"
        app = "http://" + ctr_ip_on(cid, net) + ":" + str(APP_PORT)
        if not wait_ready(app, 300):
            raise CiError("HTTP")
        dock(["network", "disconnect", "bridge", cid], timeout=60)
        app = "http://" + assert_only_net(cid, net) + ":" + str(APP_PORT)
        retained_session = run_cold_cases(app, home, cid, expected)
        dock(["stop", "--time=20", cid], timeout=30)
        dock(["rm", cid], timeout=30)
        CREATED["containers"].remove(cid)
        budget()
        cfg_warm = vol_create("cfg-warm")
        seed_volumes(home, cfg_warm, config_json(gateway, sim_port))
        cid_warm = app_create(net, home, cfg_warm)
        dock(["start", cid_warm], timeout=180)
        CURRENT[0] = "warm_persistence_and_sharing"
        app_warm = "http://" + assert_only_net(cid_warm, net) + ":" + str(APP_PORT)
        if not wait_ready(app_warm, 180):
            raise CiError("HTTP")
        run_warm_cases(app_warm, retained_session, cid_warm)
        dock(["rm", "-f", cid_warm], timeout=120)
        CREATED["containers"].remove(cid_warm)
        budget()
        cfg_broken = vol_create("cfg-broken")
        seed_volumes(home, cfg_broken, config_json(gateway, sim_port))
        cid_broken = app_create(net, home, cfg_broken, {"CONTEXT_MODE_SECURITY_BUNDLE_PATH": "/probe/broken-security.mjs"})
        dock(["start", cid_broken], timeout=180)
        CURRENT[0] = "broken_security_fail_closed"
        app_broken = "http://" + assert_only_net(cid_broken, net) + ":" + str(APP_PORT)
        if not wait_ready(app_broken, 180):
            raise CiError("HTTP")
        run_broken_case(app_broken)
        dock(["rm", "-f", cid_broken], timeout=120)
        CREATED["containers"].remove(cid_broken)
    except CiError as exc:
        record_error(exc.scope)
    except Exception as exc:
        record_error("UNEXPECTED", type(exc).__name__)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if server is not None:
            try:
                server.shutdown(); server.server_close()
            except Exception:
                pass
        OBSERVATIONS["failure_markers"] = []
        if OBSERVATIONS["error"]:
            for cid in CREATED["containers"]:
                OBSERVATIONS["failure_markers"].extend(failure_markers(cid))
        ok = cleanup()
        finish("cleanup", ok, "all_removed" if ok else "cleanup_failed")
    return summarize()

def _signal_handler(signum, frame):
    raise CiError("INTERRUPTED")

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    sys.exit(run())
