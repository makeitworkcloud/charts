#!/usr/bin/env python3
"""Build-time, deliberate rewrite of the upstream python_kubernetes kernelspec
for this fixture's layout. Parent-verified upstream argv at EG
0344929cbca688440ba1bc8f5faa074fe54bd595:
  [<python>,
   /usr/local/share/jupyter/kernels/python_kubernetes/scripts/launch_kubernetes.py,
   --RemoteProcessProxy.kernel-id {kernel_id},
   --RemoteProcessProxy.port-range {port_range},
   --RemoteProcessProxy.response-address {response_address},
   --RemoteProcessProxy.public-key {public_key}]
metadata.process_proxy.class_name is
enterprise_gateway.services.processproxies.k8s.KubernetesProcessProxy and
metadata.config.image_name defaults to elyra/kernel-py:VERSION. argv[0] and
argv[1] are replaced with the fixture venv interpreter and copied launcher
path, and config.image_name is replaced with the fixture worker image; no
launcher environment context is inferred here. Fails the image build on any
structural surprise and never prints argv or env values."""

import argparse
import json
import os
import re
import sys

EXPECTED_PROXY_CLASS = "enterprise_gateway.services.processproxies.k8s.KubernetesProcessProxy"
REMOTE_ARG_PREFIXES = (
    "--RemoteProcessProxy.kernel-id",
    "--RemoteProcessProxy.port-range",
    "--RemoteProcessProxy.response-address",
    "--RemoteProcessProxy.public-key",
)
FORBIDDEN_ENV_NAME = re.compile(
    r"(?i)(token|secret|password|passphrase|credential|privatekey|private_key|apikey|api_key)"
)


def check(condition, message):
    if not condition:
        print("KERNELSPEC_PATCH_FAIL: %s" % message, file=sys.stderr)
        sys.exit(1)


def patch_shebang(path, interpreter):
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()
    if lines and lines[0].startswith("#!"):
        lines[0] = "#!%s\n" % interpreter
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
    os.chmod(path, 0o755)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernelspec", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--interpreter", required=True)
    parser.add_argument("--worker-image", required=True)
    args = parser.parse_args()

    spec_path = os.path.join(args.kernelspec, "kernel.json")
    check(os.path.isfile(spec_path), "kernel.json missing")
    with open(spec_path, "r", encoding="utf-8") as handle:
        doc = json.load(handle)

    argv = doc.get("argv")
    check(isinstance(argv, list) and len(argv) >= 2 + len(REMOTE_ARG_PREFIXES), "argv shape")

    patched = list(argv)
    patched[0] = args.interpreter
    patched[1] = args.launcher
    check(os.path.isfile(patched[0]), "interpreter missing in image")
    check(os.path.isfile(patched[1]), "launcher missing in image")
    remote_args = [
        element
        for element in patched[2:]
        if isinstance(element, str) and any(element.startswith(prefix) for prefix in REMOTE_ARG_PREFIXES)
    ]
    check(len(remote_args) >= len(REMOTE_ARG_PREFIXES), "RemoteProcessProxy args missing")
    for element in patched:
        check(isinstance(element, str) and "\n" not in element, "argv element malformed")

    metadata = doc.get("metadata") or {}
    proxy = metadata.get("process_proxy") or {}
    check(proxy.get("class_name") == EXPECTED_PROXY_CLASS, "process proxy class mismatch")
    metadata.setdefault("config", {})["image_name"] = args.worker_image

    env_names = doc.get("env") or {}
    offenders = sorted(name for name in env_names if FORBIDDEN_ENV_NAME.search(name))
    check(not offenders, "credential-shaped env names in kernelspec")

    doc["argv"] = patched
    doc["metadata"] = metadata
    with open(spec_path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2, sort_keys=True)
        handle.write("\n")

    patch_shebang(args.launcher, args.interpreter)
    print("KERNELSPEC_PATCH_OK")


if __name__ == "__main__":
    main()
