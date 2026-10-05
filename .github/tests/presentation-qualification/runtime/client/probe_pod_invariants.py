#!/usr/bin/env python3
"""Runtime pod invariants for live kernel pods. Reads `kubectl get -o json`
from stdin and asserts security properties by NAME and BOOLEAN only -- env
values, rendered manifests, and logs are never printed or stored."""

import json
import re
import sys

FORBIDDEN_ENV_NAME = re.compile(
    r"(?i)(token|secret|password|passphrase|credential|privatekey|private_key|apikey|api_key)"
)
FORBIDDEN_VOLUME_KEYS = ("hostPath", "secret", "configMap", "persistentVolumeClaim", "projected")


def fail(message):
    print("POD_INVARIANTS_FAIL: %s" % message, file=sys.stderr)
    sys.exit(5)


def main():
    argv = sys.argv[1:]
    all_namespaces = "--all-namespaces" in argv
    positional = [arg for arg in argv if not arg.startswith("--")]
    if len(positional) != 2:
        fail("usage: probe_pod_invariants.py <namespace> <worker-image> [--all-namespaces]")
    namespace, worker_image = positional

    doc = json.load(sys.stdin)
    items = doc.get("items") or []
    if not items:
        if all_namespaces:
            print("POD_INVARIANTS_OK pods=0")
            return
        fail("no kernel pods found")

    for pod in items:
        meta = pod.get("metadata", {})
        if meta.get("namespace") != namespace:
            fail("kernel pod outside fixed namespace: %s" % meta.get("namespace"))
        labels = meta.get("labels") or {}
        if labels.get("component") != "kernel":
            fail("kernel pod missing component=kernel label (k8s.py proxy selector)")
        spec = pod.get("spec", {})
        if spec.get("automountServiceAccountToken") is not False:
            fail("automountServiceAccountToken is not false")
        if spec.get("serviceAccountName") != "pptx-worker":
            fail("kernel pod service account is not pptx-worker")
        for volume in spec.get("volumes") or []:
            if any(key in volume for key in FORBIDDEN_VOLUME_KEYS):
                fail("forbidden volume type present")

        containers = spec.get("containers") or []
        if not containers:
            fail("no containers")
        container = containers[0]
        if container.get("image") != worker_image:
            fail("kernel image is not the pinned worker image")
        env_entries = container.get("env") or []
        if any("valueFrom" in entry for entry in env_entries):
            fail("env valueFrom present")
        names = [entry["name"] for entry in env_entries]
        offenders = sorted({n for n in names if FORBIDDEN_ENV_NAME.search(n)})
        if offenders:
            fail("credential-shaped env names present: %s" % ",".join(offenders))
        values = {entry["name"]: entry.get("value") for entry in env_entries}
        if values.get("LOG_LEVEL") != "30" or values.get("EG_LOG_LEVEL") != "30":
            fail("kernel launcher log level not pinned to 30")

        container_sc = container.get("securityContext") or {}
        if container_sc.get("allowPrivilegeEscalation") is not False:
            fail("privilege escalation not disabled")
        if container_sc.get("readOnlyRootFilesystem") is not True:
            fail("root filesystem not read-only")
        drops = (container_sc.get("capabilities") or {}).get("drop") or []
        if "ALL" not in drops:
            fail("capabilities not fully dropped")

        pod_sc = spec.get("securityContext") or {}
        if (pod_sc.get("runAsUser"), pod_sc.get("runAsGroup"), pod_sc.get("fsGroup")) != (1000, 1000, 1000):
            fail("not pinned to uid/gid/fsGroup 1000")
        if (pod_sc.get("seccompProfile") or {}).get("type") != "RuntimeDefault":
            fail("seccomp not RuntimeDefault")

    print("POD_INVARIANTS_OK pods=%d" % len(items))


if __name__ == "__main__":
    main()
