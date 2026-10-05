#!/usr/bin/env python3
"""Build-time assertion of the rendered kernel pod template inside the gateway
image. Runs with the image's pinned jinja2/pyyaml, so the template variable
contract and every literal security pin are verified before the image can even
finish building."""

import argparse
import os
import sys

import yaml
from jinja2 import Environment

EXPECTED_ENV = {
    "KERNEL_ID": None,
    "LOG_LEVEL": "30",
    "EG_LOG_LEVEL": "30",
    "HOME": "/job/home",
    "TMPDIR": "/job/tmp",
}
LAUNCHER = "/usr/local/bin/kernel-launchers/python/scripts/launch_ipykernel.py"
LICENSE = "/usr/local/bin/kernel-launchers/LICENSE.md"


def check(condition, message):
    if not condition:
        print("RENDER_CHECK_FAIL: %s" % message, file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--worker-image", required=True)
    args = parser.parse_args()

    with open(args.template, "r", encoding="utf-8") as handle:
        source = handle.read()
    context = {"kernel_id": "11111111-2222-3333-4444-555555555555"}
    rendered = Environment().from_string(source).render(context)
    doc = yaml.safe_load(rendered)

    check(doc["apiVersion"] == "v1" and doc["kind"] == "Pod", "not a Pod")
    meta = doc["metadata"]
    check(meta["namespace"] == "pptx-jobs", "namespace not pinned to pptx-jobs")
    check(meta["name"] == "kernel-" + context["kernel_id"], "pod name does not track kernel_id")
    labels = meta["labels"]
    check(labels.get("kernel_id") == context["kernel_id"], "kernel_id label missing")
    check(labels.get("component") == "kernel", "component=kernel label missing (k8s.py selects by kernel_id,component=kernel)")
    check(labels.get("app") == "pptx-qualification-kernel", "app label missing")

    spec = doc["spec"]
    check(spec["automountServiceAccountToken"] is False, "SA token automount not disabled")
    check(spec["serviceAccountName"] == "pptx-worker", "wrong service account")
    check(spec["restartPolicy"] == "Never", "restart policy not Never")

    pod_sc = spec["securityContext"]
    check(
        (pod_sc["runAsUser"], pod_sc["runAsGroup"], pod_sc["fsGroup"]) == (1000, 1000, 1000),
        "not pinned to uid/gid 1000",
    )
    check(pod_sc["seccompProfile"]["type"] == "RuntimeDefault", "seccomp not RuntimeDefault")

    container = spec["containers"][0]
    check(container["image"] == args.worker_image, "image not pinned to worker image")
    check(container["imagePullPolicy"] == "IfNotPresent", "pull policy not IfNotPresent")
    check(container["command"][0] == "/bin/sh" and container["command"][1] == "-c", "command is not shell-forwarded")
    script = container["command"][2]
    check(LAUNCHER in script, "launcher path missing from command")
    check(os.path.isfile(LAUNCHER), "upstream launcher not present at pinned path")
    check("--cluster-type none" in script, "--cluster-type none missing")
    for var in ("KERNEL_ID", "PUBLIC_KEY", "RESPONSE_ADDRESS", "PORT_RANGE"):
        check('"$%s"' % var in script, "env %s not forwarded as quoted argument" % var)

    env = {entry["name"]: entry.get("value") for entry in container["env"]}
    check(set(env) == set(EXPECTED_ENV), "env names deviate from allowlist: %s" % sorted(set(env) ^ set(EXPECTED_ENV)))
    for name, value in EXPECTED_ENV.items():
        if value is not None:
            check(env.get(name) == value, "env %s != %s" % (name, value))
    check(all("valueFrom" not in entry for entry in container["env"]), "valueFrom present in env")

    container_sc = container["securityContext"]
    check(container_sc["allowPrivilegeEscalation"] is False, "privilege escalation allowed")
    check(container_sc["readOnlyRootFilesystem"] is True, "root filesystem writable")
    check(container_sc["capabilities"]["drop"] == ["ALL"], "capabilities not fully dropped")

    volumes = spec.get("volumes") or []
    check(bool(volumes) and all("emptyDir" in volume for volume in volumes), "non-emptyDir volume present")
    check(set(container["resources"]) == {"requests", "limits"}, "resource bounds missing")

    check(os.path.isfile(LICENSE), "upstream LICENSE.md not shipped with launchers")
    print("RENDER_CHECK_OK")


if __name__ == "__main__":
    main()
