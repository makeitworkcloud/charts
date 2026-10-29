import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import uuid

from lib import observation

KERNEL = "550e8400-e29b-41d4-a716-446655440000"
OTHER = "550e8400-e29b-41d4-a716-446655440001"


class ObservationTests(unittest.TestCase):
    def test_strict_message_schema(self):
        valid = {"version": 1, "kernel_id": KERNEL}
        self.assertEqual(observation.parse_message(json.dumps(valid).encode()), KERNEL)
        invalid = [
            b"x" * 257,
            b"not-json",
            b"[]",
            json.dumps({**valid, "version": True}).encode(),
            json.dumps({**valid, "kernel_id": "not-a-uuid"}).encode(),
            json.dumps({**valid, "extra": True}).encode(),
            ('{"version":1,"version":1,"kernel_id":"%s"}' % KERNEL).encode(),
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(observation.ObservationError):
                observation.parse_message(raw)

    def test_ready_and_release_are_kernel_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / "ready.json"
            self.assertIsNone(observation.read_message(ready))
            observation.publish(ready, KERNEL)
            with self.assertRaises(observation.ObservationError):
                observation.release(directory, OTHER)
            self.assertFalse((Path(directory) / "release.json").exists())
            observation.release(directory, KERNEL)
            observation.wait_release(directory, KERNEL)
            with self.assertRaises(observation.ObservationError):
                observation.release(directory, KERNEL)

    def test_no_completion_before_matching_release(self):
        with tempfile.TemporaryDirectory() as directory:
            events = []

            def release_after_wait(_):
                self.assertEqual(
                    observation.read_message(Path(directory) / "ready.json"), KERNEL
                )
                self.assertFalse((Path(directory) / "release.json").exists())
                events.append("held")
                observation.release(directory, KERNEL)

            with mock.patch.object(observation.time, "sleep", side_effect=release_after_wait):
                observation.rendezvous(directory, KERNEL)
            events.append("released")
            self.assertEqual(events, ["held", "released"])

    def test_missing_release_times_out(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(observation.time, "monotonic", side_effect=[0, 0, 121]):
                with mock.patch.object(observation.time, "sleep"):
                    with self.assertRaises(observation.ObservationError):
                        observation.wait_release(directory, KERNEL)

    def test_wrong_or_invalid_release_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "release.json"
            observation.publish(release, OTHER)
            with self.assertRaises(observation.ObservationError):
                observation.wait_release(directory, KERNEL)
            release.write_bytes(b"invalid")
            with self.assertRaises(observation.ObservationError):
                observation.wait_release(directory, KERNEL)

    def test_stale_release_or_ready_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            observation.publish(Path(directory) / "release.json", KERNEL)
            with self.assertRaises(observation.ObservationError):
                observation.rendezvous(directory, KERNEL)
            self.assertFalse((Path(directory) / "ready.json").exists())
        with tempfile.TemporaryDirectory() as directory:
            observation.publish(Path(directory) / "ready.json", KERNEL)
            with self.assertRaises(observation.ObservationError):
                observation.rendezvous(directory, KERNEL)

    def test_full_client_cannot_execute_and_cleans_up_on_handshake_failure(self):
        client = Path(__file__).resolve().parents[1] / "runtime/client/client.py"
        tree = ast.parse(client.read_text())
        function = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "mode_full"
        )
        namespace = {
            "parse_env_args": lambda _: {},
            "start_kernel": lambda _: KERNEL,
            "ws_connect": lambda _: mock.Mock(),
            "uuid": uuid,
            "time": SimpleNamespace(time=lambda: 0),
            "await_ready": mock.Mock(),
            "observation": SimpleNamespace(
                ObservationError=observation.ObservationError,
                rendezvous=mock.Mock(side_effect=observation.ObservationError("blocked")),
            ),
            "QualificationError": RuntimeError,
            "execute_task": mock.Mock(),
            "kill_kernel": mock.Mock(),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(client), "exec"), namespace)
        args = SimpleNamespace(set_env=[], observation_dir="unused", timeout=420)
        with self.assertRaises(RuntimeError):
            namespace["mode_full"](args)
        namespace["execute_task"].assert_not_called()
        namespace["kill_kernel"].assert_called_once_with(KERNEL)

    def test_host_selectors_invariants_deadline_and_invalid_ready_messages(self):
        harness = Path(__file__).resolve().parents[1] / "runtime/run_runtime_suite.sh"
        function = re.search(
            r"(?ms)^wait_for_full_kernel\(\) \{\n.*?^\}", harness.read_text()
        ).group()
        script = r'''
set -uo pipefail
KUBECTL_BIN=fake_kubectl
KIND_CONTEXT=kind-test
NAMESPACE=pptx-jobs
WORKER_TAG=test-worker
FIXTURE_DIR=/fixture
OBSERVATION_DIR=${READY_DIR:-/observation}
fail() { exit 73; }
fake_kubectl() {
    local selector=""
    while (( $# )); do
        if [[ "$1" == -l ]]; then selector=$2; break; fi
        shift
    done
    [[ "$selector" == "app=pptx-qualification-kernel,kernel_id=$EXPECTED_ID" ]] || exit 74
    [[ "$EXPECTED_ID" == "$POD_ID" ]] || return 0
    if [[ "$*" == *jsonpath* ]]; then printf '%s' "$PHASE"; else printf '{}'; fi
}
python3() {
    if [[ "$1" == */lib/observation.py ]]; then
        if [[ "$2" == read ]]; then
            if [[ -n "${READY_DIR:-}" ]]; then
                command "$PYTHON_BIN" "$REAL_HELPER" read "$READY_DIR"
            else printf '%s' "$EXPECTED_ID"; fi
        else printf ack > "$ACK_FILE"; fi
    else
        cat > /dev/null
        return "$PROBE_RC"
    fi
}
sleep() { SECONDS=$(( SECONDS + 300 )); }
'''
        cases = [
            ("Running", "0", "$$", 0, True, "synthetic"),
            ("Running", "1", "$$", 73, False, "synthetic"),
            ("Pending", "0", "$$", 1, False, "synthetic"),
            ("Running", "0", "2147483647", 2, False, "synthetic"),
            ("Running", "0", "$$", 1, False, "missing"),
            ("Running", "0", "$$", 73, False, "malformed"),
            ("Running", "0", "$$", 73, False, "oversized"),
            ("Running", "0", "$$", 1, False, "wrong-id"),
        ]
        for phase, probe_rc, pid, expected_rc, acknowledged, ready_kind in cases:
            with self.subTest(phase=phase, probe_rc=probe_rc, pid=pid, ready=ready_kind):
                with tempfile.TemporaryDirectory() as directory:
                    ack = Path(directory) / "ack"
                    ready = Path(directory) / "ready.json"
                    if ready_kind == "malformed":
                        ready.write_bytes(b"invalid")
                    elif ready_kind == "oversized":
                        ready.write_bytes(b"x" * 257)
                    elif ready_kind == "wrong-id":
                        observation.publish(ready, OTHER)
                    env = {
                        **os.environ,
                        "EXPECTED_ID": OTHER if ready_kind == "wrong-id" else KERNEL,
                        "POD_ID": KERNEL,
                        "READY_DIR": directory if ready_kind != "synthetic" else "",
                        "PYTHON_BIN": sys.executable,
                        "REAL_HELPER": str(Path(observation.__file__).resolve()),
                        "PHASE": phase,
                        "PROBE_RC": probe_rc,
                        "ACK_FILE": str(ack),
                    }
                    result = subprocess.run(
                        ["bash", "-c", script + function + '\nwait_for_full_kernel ' + pid],
                        env=env, capture_output=True, text=True, timeout=5,
                    )
                    self.assertEqual(result.returncode, expected_rc)
                    self.assertEqual(ack.exists(), acknowledged)


if __name__ == "__main__":
    unittest.main()
