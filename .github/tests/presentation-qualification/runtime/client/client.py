#!/usr/bin/env python3
"""Fixture client for the presentation qualification core proof.

Speaks the authenticated Jupyter kernel-gateway REST + websocket API directly
from outside the cluster, runs a BUILD kernel (PptxGenJS authoring) and then a
fresh RENDER kernel (receives the bounded deck, renders via LibreOffice +
Poppler), reassembles the bounded framed transport, and verifies PPTX/PNG
artifacts. Results carry only booleans, counts, digests, and dimensions --
never environment values or credentials.

Wire protocol: jupyter-server 1.24.0 services/kernels/handlers.py on_message
does json.loads(frame) and then frame.pop('channel', None) / frame['header'],
so messages are JSON dicts {"header", "parent_header", "metadata", "content",
"channel", "buffers"} — not ZMQ-style frame arrays. Received text is length-
bounded before json.loads and unexpected binary frames are rejected. Known
limitation, documented in the fixture README: websocket-client allocates each
incoming frame internally before this bound can be applied, so the bound
limits parsing and reassembly, not the initial frame allocation.
"""

import argparse
import base64
import io
import json
import os
import sys
import time
import uuid

for _candidate in ("/fixture", "/opt/qual"):
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from lib import framing, verify_artifacts  # noqa: E402

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

import websocket  # noqa: E402
from PIL import Image  # noqa: E402

BASE_URL = os.environ.get("PQ_BASE_URL", "http://127.0.0.1:8888").rstrip("/")
KERNEL_NAME = os.environ.get("PQ_KERNEL_NAME", "presentation")
WORKER_IMAGE = os.environ.get("PQ_WORKER_IMAGE", "")
BASE_KERNEL_ENV = {
    "KERNEL_NAMESPACE": "pptx-jobs",
    "KERNEL_SERVICE_ACCOUNT_NAME": "pptx-worker",
    "KERNEL_USERNAME": "presentation",
}
BUILD_TASK_CODE = (
    "import runpy; runpy.run_path('/opt/presentation/build_task.py', run_name='__main__')"
)
MAX_WS_TEXT_CHARS = 2 * 1024 * 1024
MAX_UPLOAD_BYTES = 4 * 1024 * 1024


class QualificationError(RuntimeError):
    pass


def rest(method, path, body=None, timeout=30):
    token = os.environ.get("PQ_TOKEN", "")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE_URL + path, data=data, method=method)
    if token:
        request.add_header("Authorization", "token " + token)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except urllib.error.URLError as exc:
        raise QualificationError("gateway unreachable: %s" % exc.reason)


def start_body(extra_env):
    env = dict(BASE_KERNEL_ENV)
    if WORKER_IMAGE:
        env["KERNEL_IMAGE"] = WORKER_IMAGE
    env.update(extra_env)
    return {"name": KERNEL_NAME, "env": env}


def start_kernel(extra_env):
    status, model = rest("POST", "/api/kernels", start_body(extra_env))
    if status != 201:
        raise QualificationError("kernel start rejected with http %d" % status)
    kernel_id = model.get("id") if isinstance(model, dict) else None
    if not kernel_id:
        raise QualificationError("kernel start response missing id")
    return kernel_id


def kill_kernel(kernel_id):
    return rest("DELETE", "/api/kernels/%s" % kernel_id)[0]


def kernel_gone(kernel_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, _ = rest("GET", "/api/kernels/%s" % kernel_id)
        if status == 404:
            return True
        time.sleep(2)
    return False


def ws_connect(kernel_id):
    token = os.environ.get("PQ_TOKEN", "")
    url = "%s/api/kernels/%s/channels?token=%s" % (
        BASE_URL.replace("http://", "ws://", 1),
        kernel_id,
        token,
    )
    return websocket.create_connection(url, timeout=60)


def recv(ws, deadline):
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise QualificationError("websocket deadline exceeded")
        try:
            return ws.recv()
        except websocket.WebSocketTimeoutException:
            continue


def receive(ws, deadline):
    raw = recv(ws, deadline)
    if isinstance(raw, (bytes, bytearray)):
        raise QualificationError("unexpected binary websocket frame")
    if len(raw) > MAX_WS_TEXT_CHARS:
        raise QualificationError("websocket text frame exceeds bound")
    frame = json.loads(raw)
    if not isinstance(frame, dict) or "header" not in frame:
        raise QualificationError("malformed websocket message")
    return frame.get("header") or {}, frame.get("parent_header") or {}, frame.get("content") or {}


def send_request(ws, msg_type, content, session, parent=None):
    header = {
        "msg_id": uuid.uuid4().hex,
        "username": "pptx-qual-client",
        "session": session,
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "msg_type": msg_type,
        "version": "5.3",
    }
    message = {
        "header": header,
        "parent_header": {"msg_id": parent} if parent is not None else {},
        "metadata": {},
        "content": content,
        "channel": "shell",
        "buffers": [],
    }
    ws.send(json.dumps(message))
    return header["msg_id"]


def await_ready(ws, session, deadline):
    parent_id = send_request(ws, "kernel_info_request", {}, session)
    while time.time() < deadline:
        header, parent, _content = receive(ws, deadline)
        if header.get("msg_type") == "kernel_info_reply" and parent.get("msg_id") == parent_id:
            return True
    raise QualificationError("kernel never became ready")


def execute_task(ws, session, code, deadline):
    parent_id = send_request(
        ws,
        "execute_request",
        {
            "code": code,
            "silent": False,
            "store_history": False,
            "user_expressions": {},
            "allow_stdin": False,
        },
        session,
    )
    assembler = framing.Assembler(parent_id)
    reply = None
    idle = False
    while time.time() < deadline:
        header, parent, content = receive(ws, deadline)
        if parent.get("msg_id") != parent_id:
            assembler.feed(parent.get("msg_id") or "", "")
            continue
        msg_type = header.get("msg_type")
        if msg_type == "stream":
            assembler.feed(parent_id, content.get("text", ""))
        elif msg_type == "status" and content.get("execution_state") == "idle":
            idle = True
        elif msg_type == "execute_reply":
            reply = {"status": content.get("status")}
        elif msg_type == "error":
            reply = {"status": "error", "ename": content.get("ename")}
        if idle and reply is not None:
            break
    if reply is None or not idle:
        raise QualificationError("execute did not complete before deadline")
    if reply.get("status") != "ok":
        raise QualificationError("execute_reply status: %s" % reply.get("status"))
    return assembler


def compose_upload_code(artifact):
    data = artifact.data
    if len(data) > MAX_UPLOAD_BYTES:
        raise QualificationError("deck exceeds inline upload bound")
    payload = base64.b64encode(data).decode("ascii")
    digest = artifact.sha256
    return (
        "import os, runpy\n"
        "os.makedirs('/job/in', exist_ok=True)\n"
        "with open('/job/in/deck.b64', 'w') as _fh:\n"
        "    _fh.write(%r)\n"
        "with open('/job/in/deck.sha256', 'w') as _fh:\n"
        "    _fh.write(%r)\n"
        "runpy.run_path('/opt/presentation/render_task.py', run_name='__main__')\n"
        % (payload, digest)
    )


def parse_env_args(pairs):
    env = {}
    for item in pairs or []:
        if "=" not in item:
            raise QualificationError("bad --set-env item: %s" % item.split("=", 1)[0])
        key, value = item.split("=", 1)
        env[key] = value
    return env


def write_result(path, payload):
    if not path:
        return
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def mode_full(args):
    extra = parse_env_args(args.set_env)
    result = {"ok": False, "mode": "full"}

    build_id = start_kernel(extra)
    result["build_kernel_id"] = build_id
    try:
        ws = ws_connect(build_id)
        try:
            session = uuid.uuid4().hex
            await_ready(ws, session, time.time() + 120)
            build_assembler = execute_task(ws, session, BUILD_TASK_CODE, time.time() + args.timeout)
        finally:
            try:
                ws.close()
            except Exception:
                pass
    finally:
        try:
            kill_kernel(build_id)
        except Exception:
            pass
    result["build_kernel_terminated"] = kernel_gone(build_id)
    if not result["build_kernel_terminated"]:
        raise QualificationError("build kernel not removed before render phase")

    build_artifacts = build_assembler.finish()
    pptx = build_artifacts["deckpptx"]
    if not verify_artifacts.pptx_signature_ok(pptx.data):
        raise QualificationError("pptx signature mismatch")

    render_id = start_kernel(dict(extra))
    result["render_kernel_id"] = render_id
    result["distinct_kernel_ids"] = render_id != build_id
    try:
        ws = ws_connect(render_id)
        try:
            session = uuid.uuid4().hex
            await_ready(ws, session, time.time() + 120)
            render_assembler = execute_task(
                ws, session, compose_upload_code(pptx), time.time() + args.timeout
            )
        finally:
            try:
                ws.close()
            except Exception:
                pass
    finally:
        try:
            kill_kernel(render_id)
        except Exception:
            pass

    render_artifacts = render_assembler.finish()
    png = render_artifacts["deckpng"]
    kv = render_assembler.kv
    if kv.get("preexisting_deckpptx") != "false":
        raise QualificationError("render kernel was not fresh")
    if kv.get("render_digest_ok") != "true":
        raise QualificationError("render input digest mismatch")
    ihdr = verify_artifacts.parse_ihdr(png.data)
    image = Image.open(io.BytesIO(png.data))
    image.verify()
    image = Image.open(io.BytesIO(png.data))
    image.load()
    if list(image.size) != [ihdr["width"], ihdr["height"]]:
        raise QualificationError("decoded png size disagrees with IHDR")

    result.update(
        {
            "pptx_bytes": pptx.total_bytes,
            "pptx_chunks": pptx.total_chunks,
            "pptx_sha256": pptx.sha256,
            "pptx_signature_ok": True,
            "png_bytes": png.total_bytes,
            "png_chunks": png.total_chunks,
            "png_sha256": png.sha256,
            "png_ihdr": ihdr,
            "png_decoded": True,
            "png_decoded_size": list(image.size),
            "framing_lines": build_assembler.total_lines + render_assembler.total_lines,
            "noise_lines": build_assembler.noise_lines + render_assembler.noise_lines,
            "ignored_other_parent": build_assembler.ignored_parent + render_assembler.ignored_parent,
            "build_exit_code": build_assembler.build_exit_code,
            "render_exit_code": render_assembler.build_exit_code,
            "preexisting_deck": False,
            "render_digest_ok": True,
            "ok": True,
        }
    )
    write_result(args.out, result)
    return 0


def mode_start_wait_kill(args):
    kernel_id = start_kernel(parse_env_args(args.set_env))
    result = {"ok": False, "mode": "start-wait-kill", "kernel_id": kernel_id}
    try:
        ws = ws_connect(kernel_id)
        try:
            await_ready(ws, uuid.uuid4().hex, time.time() + args.timeout)
            time.sleep(args.hold)
            result["started"] = True
            result["ok"] = True
        finally:
            try:
                ws.close()
            except Exception:
                pass
    finally:
        try:
            kill_kernel(kernel_id)
        except Exception:
            pass
    write_result(args.out, result)
    return 0


def mode_start_expect_failure(args):
    # Truthfulness contract (security review): "rejected" may ONLY be reported
    # for an explicit non-201 kernel POST status, recorded below, after an
    # auth-positive control. A POST that is accepted and then fails (or even
    # starts) is a test failure, never laundered into a rejection.
    result = {
        "ok": False,
        "mode": "start-expect-failure",
        "rejected": False,
        "accepted": False,
        "http_status": None,
    }
    control_status, _ = rest("GET", "/api/kernelspecs")
    if control_status != 200:
        raise QualificationError("auth-positive control failed with http %d" % control_status)

    status, model = rest("POST", "/api/kernels", start_body(parse_env_args(args.set_env)))
    result["http_status"] = status
    if status != 201:
        result["rejected"] = True
        result["ok"] = True
        write_result(args.out, result)
        return 0
    result["accepted"] = True

    kernel_id = model.get("id") if isinstance(model, dict) else None
    try:
        if not kernel_id:
            raise QualificationError("accepted start returned no kernel id")
        ws = ws_connect(kernel_id)
        try:
            await_ready(ws, uuid.uuid4().hex, time.time() + args.timeout)
            result["started_unexpectedly"] = True
        finally:
            try:
                ws.close()
            except Exception:
                pass
    except Exception as exc:
        result["failure"] = type(exc).__name__
    finally:
        if kernel_id:
            try:
                kill_kernel(kernel_id)
            except Exception:
                pass
    write_result(args.out, result)
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("full", "start-wait-kill", "start-expect-failure"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--set-env", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--hold", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    try:
        if args.mode == "full":
            return mode_full(args)
        if args.mode == "start-wait-kill":
            return mode_start_wait_kill(args)
        return mode_start_expect_failure(args)
    except QualificationError as exc:
        write_result(args.out, {"ok": False, "mode": args.mode, "reason": str(exc)})
        print("qualification client failure: %s" % exc, file=sys.stderr)
        return 1
    except Exception as exc:
        # Unexpected exceptions may embed the token-bearing websocket URL in
        # their message; report the class name only.
        write_result(args.out, {"ok": False, "mode": args.mode, "reason": type(exc).__name__})
        print("qualification client failure: %s" % type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
