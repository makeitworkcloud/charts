import os
import re
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import template_rules as rules  # noqa: E402

FIXTURE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.abspath(os.path.join(FIXTURE_ROOT, "..", ".."))


def read(*parts):
    with open(os.path.join(*parts), "r", encoding="utf-8") as handle:
        return handle.read()


class KernelPodTemplate(unittest.TestCase):
    def setUp(self):
        self.text = read(FIXTURE_ROOT, "runtime", "k8s", "kernel-pod.yaml.j2")
        self.content = rules.strip_comments(self.text)

    def test_security_literals(self):
        for literal in rules.KERNEL_REQUIRED_LITERALS:
            self.assertIn(literal, self.content, literal)

    def test_forbidden_constructs_absent(self):
        for forbidden in rules.KERNEL_FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(forbidden, self.content, forbidden)

    def test_only_allowed_jinja_vars(self):
        self.assertLessEqual(rules.jinja_vars(self.text), rules.ALLOWED_TEMPLATE_VARS)

    def test_env_names_exact(self):
        sections = rules.env_section_names(self.text)
        self.assertEqual(len(sections), 1)
        self.assertEqual(set(sections[0]), rules.KERNEL_ENV_EXPECTED)

    def test_upstream_appended_env_not_templated(self):
        for name in ("PORT_RANGE", "PUBLIC_KEY", "RESPONSE_ADDRESS"):
            self.assertNotIn("name: %s" % name, self.content)

    def test_log_level_pinned_to_warning(self):
        for name in ("LOG_LEVEL", "EG_LOG_LEVEL"):
            self.assertRegex(self.content, r"name:\s*%s\s*\n\s*value:\s*\"30\"" % name)

    def test_component_kernel_label_rationale_kept_in_comment(self):
        self.assertIn("component=kernel label is REQUIRED", self.text)

    def test_placeholder_replacement(self):
        rendered = rules.replace_worker_image(self.text, "pptx-qual/worker:ci")
        self.assertNotIn(rules.WORKER_IMAGE_PLACEHOLDER, rendered)
        self.assertIn("image: pptx-qual/worker:ci", rendered)

    def test_placeholder_missing_raises(self):
        with self.assertRaises(ValueError):
            rules.replace_worker_image("no placeholder here", "img")

    def test_volumes_are_emptydir_only(self):
        self.assertEqual(self.content.count("emptyDir:"), 2)
        for forbidden in ("hostPath", "secret", "configMap", "persistentVolumeClaim", "projected"):
            self.assertNotIn(forbidden, self.content)


class GatewayManifest(unittest.TestCase):
    def setUp(self):
        self.text = read(FIXTURE_ROOT, "runtime", "k8s", "gateway.yaml.in")

    def test_env_allowlist_exact(self):
        sections = rules.env_section_names(self.text)
        self.assertEqual(len(sections), 1)
        self.assertEqual(set(sections[0]), rules.GATEWAY_ENV_EXPECTED)

    def test_placeholders_present(self):
        self.assertIn(rules.TOKEN_PLACEHOLDER, self.text)
        self.assertIn(rules.GATEWAY_IMAGE_PLACEHOLDER, self.text)

    def test_no_value_from(self):
        self.assertNotIn("valueFrom", self.text)
        self.assertNotIn("secretKeyRef", self.text)

    def test_gateway_log_level_warning(self):
        self.assertIn("--log-level=WARNING", self.text)

    def test_gateway_hardening(self):
        for literal in (
            "readOnlyRootFilesystem: true",
            "allowPrivilegeEscalation: false",
            "runAsUser: 1000",
            "runAsGroup: 1000",
        ):
            self.assertIn(literal, self.text, literal)

    def test_only_authoritative_token_env(self):
        tokenish = [n for n in rules.env_names(self.text) if rules.FORBIDDEN_ENV_NAME_RE.search(n)]
        self.assertEqual(tokenish, ["EG_AUTH_TOKEN"])


class RbacManifest(unittest.TestCase):
    def setUp(self):
        self.text = read(FIXTURE_ROOT, "runtime", "k8s", "rbac.yaml")

    def test_single_namespace_role_only(self):
        top_level_kinds = re.findall(r"^kind: (\S+)$", self.text, re.M)
        self.assertEqual(top_level_kinds.count("Role"), 1)
        self.assertNotIn("ClusterRole", self.text)

    def test_verbs_exactly_pods_crud_watch(self):
        verbs = sorted(v.strip().strip('"') for v in rules.VERBS_RE.search(self.text).group(1).split(","))
        self.assertEqual(verbs, ["create", "delete", "get", "list", "watch"])
        resources = sorted(r.strip().strip('"') for r in rules.RESOURCES_RE.search(self.text).group(1).split(","))
        self.assertEqual(resources, ["pods"])

    def test_role_is_namespace_scoped(self):
        self.assertIn("namespace: pptx-jobs", self.text)

    def test_worker_service_account_has_no_bindings(self):
        head, sep, tail = self.text.partition("subjects:")
        self.assertIn("pptx-worker", head)
        self.assertTrue(sep)
        self.assertNotIn("pptx-worker", tail)

    def test_worker_sa_token_not_mounted(self):
        self.assertIn("automountServiceAccountToken: false", self.text)


class NamespaceManifest(unittest.TestCase):
    def test_fixed_namespace(self):
        text = read(FIXTURE_ROOT, "runtime", "k8s", "namespace.yaml")
        self.assertIn("kind: Namespace", text)
        self.assertIn("name: pptx-jobs", text)


class NetworkPolicyManifest(unittest.TestCase):
    def test_static_unqualified_example(self):
        text = read(FIXTURE_ROOT, "runtime", "k8s", "networkpolicy.yaml")
        self.assertIn("never applied", text)
        self.assertIn("does NOT enforce NetworkPolicy", text)
        self.assertEqual(text.count("kind: NetworkPolicy"), 2)
        self.assertIn("Ingress", text)
        self.assertIn("Egress", text)
        self.assertIn("kubernetes.io/metadata.name: kube-system", text)
        self.assertIn("port: 53", text)


class WorkflowGovernance(unittest.TestCase):
    def setUp(self):
        self.text = read(REPO_ROOT, "workflows", "presentation-qualification.yml")

    def test_pr_only_and_path_scoped(self):
        self.assertIn("pull_request:", self.text)
        self.assertNotIn("workflow_dispatch", self.text)
        self.assertNotIn("push:", self.text)
        self.assertIn('".github/workflows/presentation-qualification.yml"', self.text)
        self.assertIn('".github/tests/presentation-qualification/**"', self.text)

    def test_permissions_and_timeout(self):
        self.assertIn("contents: read", self.text)
        self.assertEqual(self.text.count("timeout-minutes: 30"), 2)

    def test_pinned_actions_only(self):
        for action_sha in (
            "3d3c42e5aac5ba805825da76410c181273ba90b1",
            "5fda3b95a4ea91299a34e894583c3862153e4b97",
        ):
            self.assertGreaterEqual(self.text.count(action_sha), 1)
        self.assertNotIn("actions/checkout@v", self.text)
        self.assertNotIn("actions/setup-python@v", self.text)
        self.assertGreaterEqual(self.text.count("persist-credentials: false"), 3)

    def test_upstream_repository_is_verified_org(self):
        self.assertIn("repository: jupyter-server/enterprise_gateway", self.text)
        self.assertNotIn("repository: jupyter/enterprise_gateway", self.text)

    def test_no_secrets_or_artifacts(self):
        self.assertNotIn("secrets.", self.text)
        self.assertNotIn("upload-artifact", self.text)


class SuiteHygiene(unittest.TestCase):
    def setUp(self):
        self.text = read(FIXTURE_ROOT, "runtime", "run_runtime_suite.sh")

    def test_no_trace_or_secret_echo(self):
        self.assertNotIn("set -x", self.text)
        self.assertNotIn('echo "$PQ_TOKEN"', self.text)
        self.assertNotIn("secrets.", self.text)

    def test_no_raw_log_collection(self):
        self.assertNotIn("kubectl logs", self.text)
        self.assertNotIn("$KUBECTL_BIN logs", self.text)
        self.assertNotIn("--tail", self.text)
        self.assertNotIn("kubectl describe", self.text)

    def test_scoped_kubeconfig_and_context(self):
        self.assertIn("KUBECONFIG=", self.text)
        self.assertIn("--context", self.text)
        self.assertIn("trap cleanup EXIT", self.text)

    def test_port_forward_address_flag(self):
        self.assertIn("--address 127.0.0.1", self.text)
        self.assertNotIn('127.0.0.1:8888:8888"', self.text.replace("--address 127.0.0.1 8888:8888", ""))

    def test_private_work_dir_and_snapshots(self):
        self.assertIn("umask 077", self.text)
        self.assertIn("snapshot_diff.py", self.text)
        self.assertIn("pods-auth-before.json", self.text)
        self.assertIn("pods-ns-before.json", self.text)
        self.assertIn("assert_snapshots_clean", self.text)

    def test_auth_negatives_include_kernel_post(self):
        self.assertIn("--data '{\"name\":\"presentation\",\"env\":{}}'", self.text)
        self.assertIn("unauth_post", self.text)
        self.assertIn("badtok_post", self.text)

    def test_namespace_rejection_requires_http_status(self):
        self.assertIn("http_status", self.text)
        self.assertIn("status != 201", self.text)


class ImageAndClientSources(unittest.TestCase):
    def setUp(self):
        self.pins = read(FIXTURE_ROOT, "pins.env")
        self.pins_values = dict(
            line.split("=", 1)
            for line in self.pins.splitlines()
            if "=" in line and not line.strip().startswith("#")
        )

    def test_dockerfiles_use_arg_base_image_and_suite_pins_it(self):
        worker = read(FIXTURE_ROOT, "runtime", "images", "worker.Dockerfile")
        gateway = read(FIXTURE_ROOT, "runtime", "images", "gateway.Dockerfile")
        suite = read(FIXTURE_ROOT, "runtime", "run_runtime_suite.sh")
        self.assertIn("ARG BASE_IMAGE", worker)
        self.assertIn("ARG BASE_IMAGE", gateway)
        self.assertIn('--build-arg BASE_IMAGE="$NODE_BASE_IMAGE"', suite)

    def test_worker_runtime_packages(self):
        worker = read(FIXTURE_ROOT, "runtime", "images", "worker.Dockerfile")
        for package in ("python3", "python3-venv", "libreoffice-impress", "poppler-utils", "fonts-liberation", "fontconfig"):
            self.assertIn(package, worker, package)

    def test_upstream_license_copied_alongside_launchers(self):
        worker = read(FIXTURE_ROOT, "runtime", "images", "worker.Dockerfile")
        gateway = read(FIXTURE_ROOT, "runtime", "images", "gateway.Dockerfile")
        self.assertIn("COPY upstream-eg/LICENSE.md /usr/local/bin/kernel-launchers/LICENSE.md", worker)
        self.assertIn("COPY upstream-eg/LICENSE.md /usr/local/bin/kernel-launchers/LICENSE.md", gateway)

    def test_license_copy_matches_render_check_assertion(self):
        gateway = read(FIXTURE_ROOT, "runtime", "images", "gateway.Dockerfile")
        render_check = read(FIXTURE_ROOT, "runtime", "images", "gateway_files", "render_check.py")
        self.assertIn("/usr/local/bin/kernel-launchers/LICENSE.md", gateway)
        self.assertIn('LICENSE = "/usr/local/bin/kernel-launchers/LICENSE.md"', render_check)

    def test_gateway_replaces_template_after_upstream_copy(self):
        gateway = read(FIXTURE_ROOT, "runtime", "images", "gateway.Dockerfile")
        upstream_copy = gateway.index("COPY upstream-eg/etc/kernel-launchers")
        template_copy = gateway.index("kernel-pod.yaml.j2")
        self.assertLess(upstream_copy, template_copy)
        self.assertIn("render_check.py", gateway)

    def test_gateway_pip_distribution_and_kernelspec_patch(self):
        gateway = read(FIXTURE_ROOT, "runtime", "images", "gateway.Dockerfile")
        self.assertIn('jupyter-enterprise-gateway=="$ENTERPRISE_GATEWAY"', gateway)
        self.assertNotIn("enterprise-gateway==", gateway.replace("jupyter-enterprise-gateway==", ""))
        self.assertIn("kernelspec_patch.py", gateway)

    def test_pins_resolve_in_build_inputs(self):
        worker = read(FIXTURE_ROOT, "runtime", "images", "worker.Dockerfile")
        for key in ("JUPYTER_CLIENT", "IPYKERNEL", "PYZMQ", "PYCRYPTODOMEX"):
            self.assertIn("$%s" % key, worker, key)
        gateway = read(FIXTURE_ROOT, "runtime", "images", "gateway.Dockerfile")
        for key in (
            "ENTERPRISE_GATEWAY",
            "JUPYTER_CLIENT",
            "PYZMQ",
            "KUBERNETES_PY",
            "JINJA2",
            "PYYAML",
            "REQUESTS",
            "WEBSOCKET_CLIENT",
            "PILLOW",
        ):
            self.assertIn("$%s" % key, gateway, key)

    def test_no_cryptodome_without_x(self):
        worker = read(FIXTURE_ROOT, "runtime", "images", "worker.Dockerfile")
        self.assertIn("pycryptodomex==", worker)
        self.assertNotIn("pycryptodome==", worker)
        self.assertEqual(self.pins_values["PYCRYPTODOMEX"].strip(), "3.20.0")
        self.assertNotIn("PYCRYPTODOME=", self.pins)

    def test_jinja2_not_vulnerable_pin(self):
        self.assertEqual(self.pins_values["JINJA2"].strip(), "3.1.6")

    def test_pptxgenjs_version_matches_pins(self):
        package_json = read(FIXTURE_ROOT, "runtime", "images", "worker_files", "package.json")
        pinned = self.pins_values["PPTXGENJS_VERSION"].strip()
        self.assertIn('"pptxgenjs": "%s"' % pinned, package_json)

    def test_worker_tasks_split_for_fresh_kernels(self):
        files = os.listdir(os.path.join(FIXTURE_ROOT, "runtime", "images", "worker_files"))
        self.assertIn("build_task.py", files)
        self.assertIn("render_task.py", files)
        self.assertNotIn("worker_task.py", files)

    def test_client_never_dumps_environment(self):
        client = read(FIXTURE_ROOT, "runtime", "client", "client.py")
        self.assertNotIn("json.dumps(os.environ", client)
        self.assertNotIn("print(os.environ", client)
        self.assertIn('"channel": "shell"', client)

    def test_probe_print_allowlist(self):
        probe = read(FIXTURE_ROOT, "runtime", "client", "probe_pod_invariants.py")
        allowed_prints = (
            'print("POD_INVARIANTS_FAIL: %s" % message, file=sys.stderr)',
            'print("POD_INVARIANTS_OK pods=%d" % len(items))',
            'print("POD_INVARIANTS_OK pods=0")',
        )
        residual = probe
        for allowed in allowed_prints:
            residual = residual.replace(allowed, "")
        self.assertNotIn("print(", residual)

    def test_snapshot_diff_name_uid_semantics(self):
        differ = read(FIXTURE_ROOT, "runtime", "client", "snapshot_diff.py")
        self.assertIn("projected namespace/name/UID", differ)
        self.assertIn(".metadata.uid", read(FIXTURE_ROOT, "runtime", "run_runtime_suite.sh"))
        self.assertIn("fixed_namespace", differ)


if __name__ == "__main__":
    unittest.main()
