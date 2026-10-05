"""Unit tests for runtime.py (mocked docker/time; no docker daemon required).

CI-only: these run in the workflow before the runtime fixture. stdlib unittest.
"""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote_plus

import runtime

MID = "mem-fixture-id-1"


def make_plugin_entry(identifier="opencode-mem", target="opencode-mem@2.28.3",
                      version=None, status="active", error=None, source_type="package"):
    source = {"type": source_type, "target": target}
    if version is not None:
        source["version"] = version
    state = {"status": status}
    if error is not None:
        state["error"] = error
    entry = {"source": source, "features": {}, "state": state}
    if identifier is not None:
        entry["id"] = identifier
    return entry


def make_plugin_payload(entries, directory="/home/opencode", with_location=True):
    payload = {"data": entries}
    if with_location:
        payload["location"] = {"directory": directory}
    return payload


def make_search_item(**fields):
    item = {"type": "memory", "id": MID, "content": runtime.MEMORY_CONTENT, "similarity": 0.9}
    item.update(fields)
    return item


def search_payload(items, success=True, error=None):
    payload = {"success": success, "data": {"items": items}}
    if error is not None:
        payload["error"] = error
    return payload


class FakeDocker:
    """Sequential scripted executor: pops one (rc, stdout, stderr) per call.
    Records (args, timeout) so budget behavior is assertable."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.scripted = script is not None
        self.calls = []

    def execute(self, args, timeout):
        self.calls.append((list(args), timeout))
        if self.script:
            result = self.script.pop(0)
            return result if len(result) == 3 else (*result, "")
        if self.scripted:
            raise AssertionError(f"Unexpected Docker call after script exhausted: {args!r}")
        return 0, "", ""

    def docker(self):
        return runtime.Docker(execute=self.execute)


class FakeHttp:
    def __init__(self, add=None, search=None):
        self.add = add if add is not None else {"success": True, "data": {"id": MID}}
        self.search = search
        self.posts = 0
        self.get_paths = []
        self.post_payloads = []

    def server_get(self, cname, path):
        return {"version": runtime.OPENCODE_VERSION, "pid": 1, "urls": {}, "paths": {}}

    def mem_get(self, cname, path):
        self.get_paths.append(path)
        if self.search is None:
            self.search = search_payload([make_search_item()])
        return self.search

    def mem_post_json(self, cname, path, payload):
        self.posts += 1
        self.post_payloads.append(payload)
        return self.add


class SanitizerTests(unittest.TestCase):
    def test_redacts_auth_material(self):
        raw = ("Authorization: Basic dXNlcjpwYXNz\nBearer abc.def\n"
               "x-opencode-mem-token: t123\npassword: hunter2\napi_key=zzz\n"
               "OPENCODE_PASSWORD=sekret\nGET https://u:p@example.com/x\n")
        out = runtime.sanitize(raw)
        for secret in ("dXNlcjpwYXNz", "abc.def", "t123", "hunter2", "zzz", "sekret", "u:p@"):
            self.assertNotIn(secret, out)

    def test_keeps_plain_diagnostics(self):
        self.assertIn("Error: ENOENT /tmp/x", runtime.sanitize("Error: ENOENT /tmp/x"))

    def test_clip_bounds_length(self):
        out = runtime.clip("x" * 10000, limit=100)
        self.assertLessEqual(len(out), 130)
        self.assertIn("[clipped]", out)


class InfoPayloadTests(unittest.TestCase):
    def test_ok(self):
        payload = {"version": runtime.OPENCODE_VERSION, "pid": 1, "urls": {}, "paths": {}}
        self.assertEqual(runtime.check_info_payload(payload), payload)

    def test_wrong_version(self):
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_info_payload({"version": "2.0.21", "pid": 1, "urls": {}, "paths": {}})
        self.assertEqual(ctx.exception.stage, "startup")

    def test_malformed_and_wrapped(self):
        for payload in (["list"], {"data": {"version": runtime.OPENCODE_VERSION}},
                        {"version": runtime.OPENCODE_VERSION}):
            with self.assertRaises(runtime.StageError):
                runtime.check_info_payload(payload)


class PluginPayloadTests(unittest.TestCase):
    def test_failed_package_without_id_reports_sanitized_cause(self):
        payload = make_plugin_payload([make_plugin_entry(identifier=None, status="failed",
                                                       error="native load failed token=raw-secret")])
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_plugin_payload(payload)
        self.assertIn("native load failed", str(ctx.exception))
        self.assertNotIn("raw-secret", str(ctx.exception))

    def test_active_package_without_id_cannot_pass(self):
        with self.assertRaises(runtime.StageError):
            runtime.check_plugin_payload(make_plugin_payload([make_plugin_entry(identifier=None)]))

    def test_ok_pinned_spec(self):
        entry = runtime.check_plugin_payload(make_plugin_payload([make_plugin_entry()]))
        self.assertEqual(entry["id"], runtime.PLUGIN_ID)

    def test_ok_package_target_with_resolved_version(self):
        payload = make_plugin_payload([make_plugin_entry(target="opencode-mem", version="2.28.3")])
        self.assertEqual(runtime.check_plugin_payload(payload)["id"], runtime.PLUGIN_ID)

    def test_id_must_be_exact(self):
        payload = make_plugin_payload([make_plugin_entry(identifier="other", target="opencode-mem@2.28.3")])
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_plugin_payload(payload)
        self.assertEqual(ctx.exception.stage, "registration")

    def test_target_must_be_pinned(self):
        payload = make_plugin_payload([make_plugin_entry(target="opencode-mem@9.9.9")])
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_plugin_payload(payload)
        self.assertEqual(ctx.exception.stage, "registration")

    def test_unresolved_target_rejected(self):
        payload = make_plugin_payload([make_plugin_entry(target="opencode-mem", version=None)])
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_plugin_payload(payload)
        self.assertEqual(ctx.exception.stage, "registration")

    def test_wrong_version_rejected(self):
        for target in ("opencode-mem@2.28.3", "opencode-mem"):
            payload = make_plugin_payload([make_plugin_entry(target=target, version="2.28.2")])
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.check_plugin_payload(payload)
            self.assertEqual(ctx.exception.stage, "registration")

    def test_failed_state_rejected_and_sanitized(self):
        payload = make_plugin_payload([make_plugin_entry(
            status="failed", error="init exploded after Bearer rawsecret was sent")])
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_plugin_payload(payload)
        self.assertEqual(ctx.exception.stage, "registration")
        self.assertIn("failed", str(ctx.exception))
        self.assertNotIn("rawsecret", str(ctx.exception))

    def test_wrapped_rejected(self):
        payload = {"location": {"directory": "/home/opencode"}, "data": {"data": [make_plugin_entry()]}}
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_plugin_payload(payload)
        self.assertEqual(ctx.exception.stage, "registration")

    def test_location_envelope_required_and_exact(self):
        for payload in (make_plugin_payload([make_plugin_entry()], with_location=False),
                        make_plugin_payload([make_plugin_entry()], directory="/tmp"),
                        {"location": {"directory": "/home/opencode"}, "data": []}):
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.check_plugin_payload(payload)
            self.assertEqual(ctx.exception.stage, "registration")


class AddResponseTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(runtime.check_add_response({"success": True, "data": {"id": MID}}), MID)

    def test_success_must_be_true_not_truthy(self):
        for bad in (1, 0, "true", [], None):
            payload = {"success": bad, "data": {"id": MID}}
            if bad is None:
                payload.pop("success")
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.check_add_response(payload)
            self.assertEqual(ctx.exception.stage, "storage")

    def test_invalid_ids_rejected(self):
        for bad in ("", None, 123, []):
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.check_add_response({"success": True, "data": {"id": bad}})
            self.assertEqual(ctx.exception.stage, "storage")

    def test_wrapped_and_malformed_rejected(self):
        for payload in ({"data": {"data": {"id": MID}}}, {"success": True}, ["x"], {"data": "id"}):
            with self.assertRaises(runtime.StageError):
                runtime.check_add_response(payload)

    def test_error_message_sanitized(self):
        payload = {"success": False, "error": "rejected token=sekrit"}
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_add_response(payload)
        self.assertNotIn("sekrit", str(ctx.exception))


class SearchResponseTests(unittest.TestCase):
    def test_ok(self):
        raw = runtime.check_search_response(search_payload([make_search_item(similarity=0.61)]),
                                            MID, runtime.MEMORY_CONTENT)
        self.assertEqual(raw, 0.61)

    def test_int_similarity_ok_and_boundary(self):
        self.assertEqual(runtime.check_search_response(
            search_payload([make_search_item(similarity=1)]), MID, runtime.MEMORY_CONTENT), 1)
        self.assertEqual(runtime.check_search_response(
            search_payload([make_search_item(similarity=0.6)]), MID, runtime.MEMORY_CONTENT), 0.6)

    def test_above_one_not_rejected_no_upper_bound(self):
        self.assertEqual(runtime.check_search_response(
            search_payload([make_search_item(similarity=1.2)]), MID, runtime.MEMORY_CONTENT), 1.2)

    def test_below_threshold_rejected(self):
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_search_response(search_payload([make_search_item(similarity=0.59)]),
                                          MID, runtime.MEMORY_CONTENT)
        self.assertEqual(ctx.exception.stage, "embedding")

    def test_nan_bool_and_non_numeric_rejected(self):
        for bad in (float("nan"), float("inf"), True, False, "0.9", None, [0.9]):
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.check_search_response(search_payload([make_search_item(similarity=bad)]),
                                              MID, runtime.MEMORY_CONTENT)
            self.assertEqual(ctx.exception.stage, "embedding")

    def test_similarity_only_no_score_fallback(self):
        item = {"type": "memory", "id": MID, "content": runtime.MEMORY_CONTENT, "score": 0.9}
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_search_response(search_payload([item]), MID, runtime.MEMORY_CONTENT)
        self.assertEqual(ctx.exception.stage, "embedding")

    def test_item_type_must_be_memory(self):
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_search_response(search_payload([make_search_item(type="summary")]),
                                          MID, runtime.MEMORY_CONTENT)
        self.assertEqual(ctx.exception.stage, "storage")

    def test_content_mismatch_rejected(self):
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_search_response(search_payload([make_search_item(content="other")]),
                                          MID, runtime.MEMORY_CONTENT)
        self.assertEqual(ctx.exception.stage, "storage")

    def test_missing_id_rejected(self):
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_search_response(search_payload(
                [make_search_item(id="other-id")]), MID, runtime.MEMORY_CONTENT)
        self.assertEqual(ctx.exception.stage, "storage")

    def test_wrapped_and_success_false_rejected(self):
        wrapped = {"success": True, "data": {"items": {"data": []}}}
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_search_response(wrapped, MID, runtime.MEMORY_CONTENT)
        self.assertEqual(ctx.exception.stage, "embedding")
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.check_search_response(search_payload([], success=False, error="boom"),
                                          MID, runtime.MEMORY_CONTENT)
        self.assertEqual(ctx.exception.stage, "embedding")


class HealthPayloadTests(unittest.TestCase):
    def test_ok(self):
        runtime.check_mem_health({"success": True, "status": "ok", "authEnabled": False})

    def test_strict_success_and_status(self):
        for payload in ({"success": 1, "status": "ok"},
                        {"success": True, "status": "down"},
                        {"status": "ok"}):
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.check_mem_health(payload)
            self.assertEqual(ctx.exception.stage, "registration")


class DeadlineTests(unittest.TestCase):
    def test_deadline_preserves_last_registration_error(self):
        clock = {"now": 0.0}
        def fail():
            raise runtime.StageError("registration", "plugin inventory is empty")
        def sleep(seconds):
            clock["now"] += seconds
        with mock.patch.object(runtime, "_now", lambda: clock["now"]), \
                mock.patch.object(runtime, "_sleep", sleep):
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.wait_until("registration", fail, deadline=2.0, interval=3.0)
        self.assertEqual(ctx.exception.stage, "registration")
        self.assertIn("inventory is empty", str(ctx.exception))

    def test_known_failed_registration_does_not_retry(self):
        calls = []
        def fail():
            calls.append(1)
            raise runtime.PluginFailedError("registration", "plugin failed: missing native library")
        with mock.patch.object(runtime, "_now", lambda: 0.0), \
                mock.patch.object(runtime, "_sleep") as sleep:
            with self.assertRaises(runtime.StageError):
                runtime.wait_until("registration", fail, deadline=100.0)
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()

    def test_wait_until_times_out_without_sleeping(self):
        clock = {"now": 0.0}
        sleeps = []

        def fake_now():
            clock["now"] += 300.0
            return clock["now"]

        def failing():
            raise runtime.StageError("startup", "not ready")

        with mock.patch.object(runtime, "_now", fake_now), \
                mock.patch.object(runtime, "_sleep", lambda s: sleeps.append(s)):
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.wait_until("readiness", failing, deadline=100.0, interval=1.0)
        self.assertEqual(ctx.exception.stage, "startup")
        self.assertIn("deadline", str(ctx.exception))
        self.assertEqual(sleeps, [])

    def test_exhausted_deadline_fails_before_check(self):
        calls = []

        def fn():
            calls.append(1)
            return "late"

        with self.assertRaises(runtime.StageError) as ctx:
            runtime.wait_until("poll", fn, deadline=runtime._now() - 10.0)
        self.assertIn("before check", str(ctx.exception))
        self.assertEqual(calls, [])

    def test_delayed_success_after_deadline_rejected(self):
        ticks = iter([0.0, 500.0])

        def fn():
            return "delayed"

        with mock.patch.object(runtime, "_now", lambda: next(ticks)):
            with self.assertRaises(runtime.StageError) as ctx:
                runtime.wait_until("poll", fn, deadline=100.0)
        self.assertIn("after deadline", str(ctx.exception))

    def test_wait_until_returns_value(self):
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise runtime.StageError("transport", "warming up")
            return 42

        with mock.patch.object(runtime, "_now", lambda: 0.0), \
                mock.patch.object(runtime, "_sleep", lambda s: None):
            self.assertEqual(runtime.wait_until("poll", flaky, deadline=100.0), 42)


class DockerBudgetTests(unittest.TestCase):
    def test_scripted_mock_rejects_extra_calls(self):
        fake = FakeDocker([(0, "ok", "")])
        fake.execute(["ps"], 10)
        with self.assertRaises(AssertionError):
            fake.execute(["ps"], 10)

    def test_slow_pull_consumes_overall_budget(self):
        fake = FakeDocker()
        docker = fake.docker()
        docker.set_deadline(runtime._now() + 100)
        docker.run(["image", "pull", "ref"], timeout=600, stage="startup")
        _args, timeout = fake.calls[0]
        self.assertTrue(0 < timeout <= 100)

    def test_no_deadline_passes_requested_timeout(self):
        fake = FakeDocker()
        fake.docker().run(["logs", "c"], timeout=600)
        self.assertEqual(fake.calls[0][1], 600)

    def test_exhausted_budget_launches_no_subprocess(self):
        fake = FakeDocker()
        docker = fake.docker()
        docker.set_deadline(runtime._now() - 1)
        with self.assertRaises(runtime.StageError):
            docker.run(["ps"], stage="cleanup")
        self.assertEqual(fake.calls, [])

    def test_cleanup_uses_separate_reset_budget(self):
        fake = FakeDocker([(1, "", "Error: No such object: c1")])
        docker = fake.docker()
        docker.set_deadline(runtime._now() - 1)  # global budget spent
        docker.set_deadline(runtime._now() + runtime.CLEANUP_BUDGET_S)  # cleanup reset
        res = runtime.Resources(docker)
        res.track_container("c1")
        res.cleanup()  # exhausted global budget does not block scoped cleanup
        args, timeout = fake.calls[0]
        self.assertEqual(args, ["container", "inspect", "c1"])
        self.assertTrue(0 < timeout <= runtime.CLEANUP_BUDGET_S)


class CleanupTests(unittest.TestCase):
    def test_cleanup_failure_fails_gate(self):
        fake = FakeDocker([(0, "", ""), (0, "", ""), (1, "", "Error: rm failed")])
        res = runtime.Resources(fake.docker())
        res.track_container("c1")
        with self.assertRaises(runtime.StageError) as ctx:
            res.cleanup()
        self.assertEqual(ctx.exception.stage, "cleanup")

    def test_stop_failure_still_removes(self):
        fake = FakeDocker([(0, "", ""), (1, "", "Error: stop timeout"), (0, "", ""),
                           (1, "", "Error: No such volume: v1")])
        res = runtime.Resources(fake.docker())
        res.track_container("c1")
        res.track_volume("v1")
        res.cleanup()  # stop failed but rm -f succeeded -> not a failure
        removed = [args for args, _t in fake.calls if args[:2] == ["rm", "-f"]]
        self.assertEqual(removed, [["rm", "-f", "c1"]])

    def test_missing_resources_are_not_failures(self):
        fake = FakeDocker([(1, "", "Error: No such object: c1"),
                           (1, "", "Error: No such volume: v1")])
        res = runtime.Resources(fake.docker())
        res.track_container("c1")
        res.track_volume("v1")
        res.cleanup()
        kinds = [args[:2] for args, _t in fake.calls]
        self.assertEqual(kinds, [["container", "inspect"], ["volume", "inspect"]])


class SecurityInspectTests(unittest.TestCase):
    def script(self, cap_add):
        return [(0, "1000:1000\n"), (0, "true\n"), (0, '["ALL"]\n'),
                (0, '["no-new-privileges"]\n'), (0, "{}\n"), (0, "bridge\n"),
                (0, cap_add + "\n"), (0, "1000\n")]

    def test_ok_null_and_empty_capadd(self):
        for cap_add in ("null", "[]"):
            fake = FakeDocker(self.script(cap_add))
            runtime.verify_security(fake.docker(), "app", "bridge")

    def test_granted_capabilities_rejected(self):
        fake = FakeDocker(self.script('["NET_ADMIN"]'))
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.verify_security(fake.docker(), "app", "bridge")
        self.assertEqual(ctx.exception.stage, "startup")

    def test_user_mismatch_fails_startup(self):
        script = self.script("null")
        script[0] = (0, "0:0\n")
        fake = FakeDocker(script)
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.verify_security(fake.docker(), "app", "bridge")
        self.assertEqual(ctx.exception.stage, "startup")


class SinglePostTests(unittest.TestCase):
    def test_post_payload_carries_content_and_container_tag(self):
        http = FakeHttp()
        self.assertEqual(runtime.add_memory(http, "c"), MID)
        self.assertEqual(http.posts, 1)
        self.assertEqual(http.post_payloads,
                         [{"content": runtime.MEMORY_CONTENT,
                           "containerTag": runtime.CONTAINER_TAG}])

    def test_duplicate_post_refused(self):
        http = FakeHttp()
        runtime.add_memory(http, "c")
        with self.assertRaises(runtime.StageError) as ctx:
            runtime.add_memory(http, "c")
        self.assertEqual(ctx.exception.stage, "storage")
        self.assertIn("duplicate", str(ctx.exception))
        self.assertEqual(http.posts, 1)

    def test_replacement_search_performs_no_post_and_tags_query(self):
        http = FakeHttp()
        similarity = runtime.search_verify(http, "c", MID)
        self.assertEqual(similarity, 0.9)
        self.assertEqual(http.posts, 0)
        path = http.get_paths[-1]
        self.assertIn("q=" + quote_plus(runtime.MEMORY_CONTENT), path)
        self.assertIn("tag=" + quote_plus(runtime.CONTAINER_TAG), path)
        self.assertIn("page=1", path)


class ConfigTests(unittest.TestCase):
    def test_seed_writes_exactly_two_pinned_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime.write_seed_files(tmp)
            self.assertEqual(sorted(os.listdir(tmp)), ["opencode-mem.jsonc", "opencode.json"])
            app = json.loads(Path(tmp, "opencode.json").read_text())
            self.assertEqual(app["plugins"], [runtime.PLUGIN_SPEC])
            self.assertEqual(app["enabled_providers"], [])
            self.assertEqual(app["permissions"],
                             [{"action": "*", "resource": "*", "effect": "deny"}])
            mem = json.loads(Path(tmp, "opencode-mem.jsonc").read_text())
            self.assertEqual(mem["storagePath"], runtime.HOME_PATH + "/.opencode-mem")
            self.assertEqual(mem["webServerApiToken"], runtime.MEM_TOKEN)
            self.assertEqual(mem["webServerPort"], runtime.MEM_PORT)
            for banned in ("opencodeProvider", "opencodeModel", "apiKey", "embeddingApiKey",
                           "userProfileAnalysisInterval"):
                self.assertNotIn(banned, mem)

    def test_seed_files_world_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime.write_seed_files(tmp)
            self.assertEqual(stat.S_IMODE(Path(tmp).stat().st_mode), 0o755)
            for name in ("opencode.json", "opencode-mem.jsonc"):
                self.assertEqual(stat.S_IMODE(Path(tmp, name).stat().st_mode), 0o644)

    def test_app_env_allowlist_single_public_credential(self):
        creds = {k: v for k, v in runtime.APP_ENV
                 if k.endswith(("PASSWORD", "TOKEN", "KEY", "SECRET"))}
        self.assertEqual(creds, {"OPENCODE_PASSWORD": runtime.BASIC_PASSWORD})
        self.assertIn(("OPENCODE_DB", "opencode.db"), runtime.APP_ENV)
        self.assertIn(("OPENCODE_PRINT_LOGS", "1"), runtime.APP_ENV)
        self.assertIn(("OPENCODE_LOG_LEVEL", "WARN"), runtime.APP_ENV)

    def test_containers_share_workdir_and_env(self):
        args1 = runtime.app_run_args("app1", "home-vol", "cfg-c1", "/tmp/seed", offline=False)
        args2 = runtime.app_run_args("app2", "home-vol", "cfg-c2", "/tmp/seed", offline=True)

        def env_of(args):
            return {args[i + 1] for i, a in enumerate(args) if a == "-e"}

        self.assertEqual(env_of(args1), env_of(args2))
        self.assertEqual(env_of(args1), {f"{k}={v}" for k, v in runtime.APP_ENV})
        self.assertEqual(args1[args1.index("--workdir") + 1], runtime.HOME_PATH)
        self.assertEqual(args2[args2.index("--workdir") + 1], runtime.HOME_PATH)

    def test_app_args_hardened_platform_offline_fresh_config(self):
        args1 = runtime.app_run_args("app1", "home-vol", "cfg-c1", "/tmp/seed", offline=False)
        args2 = runtime.app_run_args("app2", "home-vol", "cfg-c2", "/tmp/seed", offline=True)
        self.assertEqual(args2[args2.index("--network") + 1], "none")
        self.assertEqual(args1[args1.index("--network") + 1], "bridge")
        self.assertNotIn("cfg-c1", args2)
        for args in (args1, args2):
            self.assertIn("--platform", args)
            self.assertEqual(args[args.index("--platform") + 1], runtime.PLATFORM)
            self.assertNotIn("-p", args)
            self.assertFalse(any("/var/run/docker.sock" in a for a in args))
            self.assertNotIn("--privileged", args)
            self.assertEqual(args[args.index("--user") + 1], runtime.APP_USER)
            self.assertEqual(args[args.index("--cap-drop") + 1], "ALL")
            self.assertIn("--read-only", args)
            self.assertIn("--security-opt", args)
            self.assertIn(f"home-vol:{runtime.HOME_PATH}", args)
            self.assertEqual(len([a for a in args if a.endswith("/opencode.json:ro")]), 1)
            self.assertEqual(args[args.index("--entrypoint") + 1], "opencode")
            self.assertEqual(args[args.index("serve"):],
                             ["serve", "--hostname", "127.0.0.1", "--port", str(runtime.SERVER_PORT)])

    def test_preparer_entrypoint_platform_chmod_before_chown(self):
        fake = FakeDocker()
        res = runtime.Resources(fake.docker())
        runtime.seed_volume(fake.docker(), res, "prep-c1", "/tmp/seed", "cfg-c1", home_vol="home-vol")
        call = fake.calls[0][0]
        self.assertEqual(call[call.index("--platform") + 1], runtime.PLATFORM)
        self.assertEqual(call[call.index("--cap-add") + 1], "CHOWN")
        self.assertEqual(call[call.index("--cap-drop") + 1], "ALL")
        self.assertEqual(call[call.index("--network") + 1], "none")
        self.assertIn("/tmp/seed:/seed:ro", call)
        self.assertIn("home-vol:/home/opencode", call)
        image_at = call.index(runtime.IMAGE)
        self.assertLess(call.index("--entrypoint"), image_at)
        self.assertEqual(call[image_at - 1], "sh")
        self.assertEqual(call[image_at + 1], "-c")
        script = call[image_at + 2]
        self.assertLess(script.index("chmod"), script.index("chown"))
        self.assertEqual(script.count("chmod"), 1)
        self.assertEqual(script.count("chown"), 1)
        self.assertIn("prep-c1", res.containers)

    def test_replacement_preparer_touches_config_volume_only(self):
        fake = FakeDocker()
        res = runtime.Resources(fake.docker())
        runtime.seed_volume(fake.docker(), res, "prep-c2", "/tmp/seed", "cfg-c2", home_vol=None)
        call = fake.calls[0][0]
        self.assertFalse(any(a.startswith("home-vol:") for a in call))
        script = call[call.index(runtime.IMAGE) + 2]
        self.assertEqual(script.count("chmod"), 1)
        self.assertEqual(script.count("chown"), 1)
        self.assertTrue(script.endswith("/home/opencode/.config"))

    def test_resources_tracked_before_creation(self):
        seen = {}

        def execute(args, timeout):
            if args[:2] == ["volume", "create"]:
                seen["volumes_at_create"] = list(res.volumes)
            if args[0] == "run" and "--name" in args:
                seen["containers_at_run"] = list(res.containers)
            return 0, "", ""

        res = runtime.Resources(runtime.Docker(execute=execute))
        runtime.create_volume(res.docker, res, "v-new")
        self.assertEqual(seen["volumes_at_create"], ["v-new"])
        runtime.seed_volume(res.docker, res, "prep-x", "/seed", "cfg-x")
        self.assertEqual(seen["containers_at_run"], ["prep-x"])


class DiagnosticsTests(unittest.TestCase):
    def test_merges_stderr_filters_and_sanitizes(self):
        fake = FakeDocker([(0, "ordinary startup line\nError: boom token=sekret\n",
                            "native stderr Error: wget exit 4\n")])
        res = runtime.Resources(fake.docker())
        res.track_container("c1")
        out = runtime.diagnostics(fake.docker(), res)
        self.assertIn("wget exit 4", out)          # stderr merged despite rc 0
        self.assertIn("boom", out)
        self.assertNotIn("sekret", out)            # credential-like content redacted
        self.assertNotIn("ordinary startup line", out)  # allow-list only, no raw logs
        self.assertIn("c1", out)


class ImagePinTests(unittest.TestCase):
    def test_pins_are_consistent(self):
        self.assertIn("2.0.22@", runtime.IMAGE)
        self.assertTrue(runtime.IMAGE.split("@", 1)[1].startswith("sha256:"))
        self.assertEqual(runtime.PLATFORM, "linux/amd64")
        self.assertEqual(runtime.PLUGIN_SPEC, f"{runtime.PLUGIN_ID}@{runtime.PLUGIN_VERSION}")
        self.assertTrue(runtime.CONTAINER_TAG.startswith("sm_project_"))
        self.assertEqual(runtime.SIMILARITY_THRESHOLD, 0.6)


if __name__ == "__main__":
    unittest.main()
