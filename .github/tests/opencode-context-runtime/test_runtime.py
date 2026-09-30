import contextlib
import hashlib
import io
import json
import tarfile
import unittest
import uuid
from urllib.request import Request
from unittest.mock import patch

import runtime


class FixtureTests(unittest.TestCase):
    def test_native_configuration(self):
        config = runtime.config_json("127.0.0.1", 12345)
        self.assertEqual(config["enabled_providers"], ["fixture"])
        self.assertEqual(config["plugin"], ["context-mode@1.0.169"])
        self.assertEqual(config["mcp"], {})
        self.assertNotIn("agents", config)
        self.assertEqual(config["permission"]["*"], "deny")
        self.assertEqual(config["agent"]["restricted"]["permission"], {"*": "deny"})
        self.assertEqual(config["agent"]["ask"]["permission"]["ctx_index"], "ask")

    def test_stale_call_cannot_pass(self):
        old, new = uuid.uuid4().hex, uuid.uuid4().hex
        part = {"type": "tool", "tool": "ctx_search", "callID": "call_" + old,
                "state": {"status": "completed", "input": {}, "output": "old"}}
        self.assertIsNone(runtime.find_tool_part([{"parts": [part]}], "ctx_search", new))
        self.assertEqual(runtime.find_tool_part([{"parts": [part]}], "ctx_search", old), part)

    def test_wrong_input_cannot_pass(self):
        case = uuid.uuid4().hex
        runtime.register_plan(case, "ctx_index", {"content": "expected"})
        self.assertFalse(runtime.expected_input({"state": {"input": {"content": "wrong"}}}, case))

    def test_query_echo_is_not_recall(self):
        part = {"state": {"status": "completed", "output": "## " + runtime.MARKER + "\nNo results"}}
        self.assertFalse(runtime.recall_hit(part))
        part["state"]["output"] += "\nfixture-a: " + runtime.MARKER
        self.assertTrue(runtime.recall_hit(part))
        part["state"]["status"] = "error"
        self.assertFalse(runtime.recall_hit(part))

    def test_simulator_uses_latest_user_case(self):
        server, port = runtime.start_sim("127.0.0.1")
        old, new = uuid.uuid4().hex, uuid.uuid4().hex
        runtime.register_plan(old, "ctx_index", {"content": "old"})
        runtime.register_plan(new, "ctx_search", {"queries": ["new"]})
        body = {"stream": True, "messages": [
            {"role": "user", "content": "CASE:" + old},
            {"role": "user", "content": [{"type": "text", "text": "CASE:" + new}]}],
            "tools": [{"type": "function", "function": {"name": "ctx_search"}}]}
        try:
            request = Request("http://127.0.0.1:" + str(port) + "/v1/chat/completions",
                              data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with runtime.LOCAL_HTTP.open(request, timeout=5) as response:
                text = response.read().decode()
            self.assertIn("call_" + new, text)
            self.assertNotIn("call_" + old, text)
            self.assertIn("ctx_search", text)
            self.assertEqual(runtime.case_obs(new)["offered"], {"ctx_search"})
        finally:
            server.shutdown()
            server.server_close()

    def test_resume_observation_is_system_only(self):
        server, port = runtime.start_sim("127.0.0.1")
        case = uuid.uuid4().hex
        runtime.register_plan(case, None, {})
        body = {"messages": [{"role": "user", "content": "CASE:" + case + " " + runtime.RESUME_MARKER}]}
        try:
            request = Request("http://127.0.0.1:" + str(port) + "/v1/chat/completions",
                              data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with runtime.LOCAL_HTTP.open(request, timeout=5) as response:
                response.read()
            self.assertIs(runtime.case_obs(case)["marker_first"], False)
        finally:
            server.shutdown()
            server.server_close()

    def test_unexecuted_gate_fails_aggregate(self):
        saved = {key: dict(value) for key, value in runtime.RESULTS.items()}
        try:
            for key in runtime.RESULTS:
                runtime.finish(key, True)
            runtime.RESULTS["resume_isolation_gate"]["status"] = "NOT_RUN"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runtime.summarize(), 1)
        finally:
            runtime.RESULTS.update(saved)

    def test_abort_failure_is_not_swallowed(self):
        with patch.object(runtime, "app_http", return_value=(500, None)), patch.object(runtime, "await_idle") as idle:
            with self.assertRaises(runtime.CiError):
                runtime.abort_session("http://127.0.0.1", "/synthetic", "synthetic-session")
            idle.assert_not_called()

    def test_cleanup_deadline_prevents_later_command(self):
        with patch.object(runtime, "CLEANING", True), patch.object(runtime, "CLEANUP_DEADLINE", 0), patch.object(runtime.subprocess, "run") as run:
            with self.assertRaises(runtime.CiError):
                runtime.dock(["rm", "-f", "synthetic-container"])
            run.assert_not_called()

    def test_installed_archive_uses_top_level_manifest(self):
        files = {"context-mode/nested/package.json": b'{"name":"other","version":"0"}'}
        files.update({"context-mode/" + rel: b"synthetic compiled file" for rel in runtime.SELECTED_MEMBERS})
        files["context-mode/package.json"] = json.dumps({"name": "context-mode", "version": runtime.PLUGIN_VERSION}).encode()
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w") as archive:
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        hashes = runtime.installed_package_hashes(payload.getvalue())
        self.assertEqual(hashes["package.json"], hashlib.sha256(files["context-mode/package.json"]).hexdigest())

    def test_terminal_error_is_not_a_completed_approval_bypass(self):
        case = uuid.uuid4().hex
        runtime.register_plan(case, "ctx_index", {"content": "synthetic"})
        part = {"state": {"status": "error", "input": {"content": "synthetic"}}}
        self.assertEqual(runtime.approval_outcome(False, part, part, True, False, case),
                         (False, "terminal_error_without_approval"))
        part["state"]["status"] = "completed"
        self.assertEqual(runtime.approval_outcome(False, part, part, True, False, case),
                         (False, "bypass_completed"))

    def test_unavailable_database_is_not_proof_of_no_side_effect(self):
        case = uuid.uuid4().hex
        runtime.register_plan(case, "ctx_index", {"content": "synthetic"})
        self.assertEqual(runtime.approval_outcome(True, None, None, True, None, case),
                         (False, "absence_unverified"))


if __name__ == "__main__":
    unittest.main()
