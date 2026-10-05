# Presentation qualification — FIRST stage (CI-only core proof)

This directory is a self-contained CI fixture for the makeitworkcloud/charts
repository. It proves, on a disposable hosted-runner Kubernetes cluster, the
core runtime claims of the proposed internal PPTX MCP + Jupyter Enterprise
Gateway design. It is **not** a production backend, chart change, or GitOps
rollout: nothing outside `.github/workflows/presentation-qualification.yml`
and `.github/tests/presentation-qualification/` is touched, and the
opencode-server chart is deliberately unmodified (no `Chart.yaml`, version,
config, or Deployment edits).

## Qualification status semantics (no silent skips, no false overall PASS)

The runtime suite emits three separate statuses and writes
`qualification-status.json` plus a job step summary:

| Field | Meaning | Value in this fixture |
| --- | --- | --- |
| `core_rbac_render_transport` | fixed-namespace RBAC, pod hardening, authenticated REST+websocket, fresh build+render kernels, bounded digest-verified transport, cancellation | `PASS` gates CI |
| `network_isolation` | NetworkPolicy enforcement with negative probing | always `INCOMPLETE` here |
| `overall` | never claimed from a partial scope | always `INCOMPLETE` here |

This FIRST fixture always runs kind's default kindnet CNI, which does **not**
enforce NetworkPolicy. `runtime/k8s/networkpolicy.yaml` is a static,
unqualified example: it is never applied, and no isolation is claimed from
manifest text. There is deliberately no optional CNI branch and no pins for
one; network isolation cannot be promoted inside this fixture. The CI exit
gate covers core scope only. The canonical cluster context is documented
in-repo (flannel with a dated NetworkPolicy waiver in the mcp-gateway
workloads area); production remains blocked on a target-CNI negative proof
regardless of what this CI fixture shows.

## Core proof flow

1. **Disposable cluster** — kind v0.30.0 binary (SHA256-verified) creating a
   `kindest/node:v1.33.4@sha256:…` single-node cluster into a scoped runner
   temp kubeconfig written under `umask 077`; every kubectl call uses the
   explicit `kind-pptx-qual` context. Binary install is used instead of
   helm/kind-action per parent preference (that action pin was verified but
   is intentionally unused).
2. **Gateway** — Jupyter Enterprise Gateway 3.3.0 (pip distribution
   `jupyter-enterprise-gateway`) at upstream revision
   `0344929cbca688440ba1bc8f5faa074fe54bd595`, running as an in-cluster pod
   (required: `enterprise_gateway/services/processproxies/k8s.py` imports
   `config.load_incluster_config` at module level). Its service account holds
   exactly one namespace-scoped Role: get/list/watch/create/delete on `pods`
   in `pptx-jobs`. Auth is a synthetic per-run `EG_AUTH_TOKEN`; unauthenticated
   and wrong-token GET **and kernel POST** requests must be rejected 401/403
    with label-independent all-namespace snapshots showing no observed pod
    endpoint differences, not a continuous zero-side-effect proof.
3. **Kernelspec replacement (deliberate, at build)** — the upstream
   `python_kubernetes` kernelspec is copied and then rewritten by
   `kernelspec_patch.py`: parent-verified upstream argv is
   `[<python>, /usr/local/share/jupyter/kernels/python_kubernetes/scripts/launch_kubernetes.py,
   --RemoteProcessProxy.kernel-id {kernel_id}, --RemoteProcessProxy.port-range {port_range},
   --RemoteProcessProxy.response-address {response_address},
   --RemoteProcessProxy.public-key {public_key}]` with
   `metadata.process_proxy.class_name` =
   `enterprise_gateway.services.processproxies.k8s.KubernetesProcessProxy` and
   `metadata.config.image_name` defaulting to `elyra/kernel-py:VERSION`. The
   patch replaces argv[0] with `/opt/venv/bin/python` (upstream assumes
   `/opt/conda/bin/python`), argv[1] with the copied launcher at
   `/usr/local/bin/kernel-launchers/kubernetes/scripts/launch_kubernetes.py`,
   and `config.image_name` with the fixture worker image; the launcher
   shebang is rewritten to the same venv interpreter. The build fails on any
   structural surprise. Nothing about the launcher's env context is inferred,
   and argv/env values are never printed anywhere in this fixture.
4. **Fixed kernel pod template** — the fixture-authored
   `runtime/k8s/kernel-pod.yaml.j2` is installed at the exact path
   `launch_kubernetes.py` reads (template adjacent to the script) and replaces
   upstream's. Every security-relevant knob is a literal: namespace
   `pptx-jobs`, build-time image pin, `serviceAccountName: pptx-worker`,
   `automountServiceAccountToken: false`, uid/gid/fsGroup 1000,
   `readOnlyRootFilesystem: true`, drop ALL, no privilege escalation, seccomp
   `RuntimeDefault`, `restartPolicy: Never`, emptyDir-only bounded volumes.
   The `component: kernel` label is mandatory: k8s.py `get_container_status`
   (line 109 at the pinned revision) selects pods with
   `label_selector='kernel_id=<id>,component=kernel'` — without it the proxy
   cannot find the worker pod.
5. **Env contract (source-backed)** — `launch_kubernetes.py` maps only
   `KERNEL_*` env vars to Jinja keywords; `PORT_RANGE`, `PUBLIC_KEY`, and
   `RESPONSE_ADDRESS` are placed in the launcher process environment by the
   gateway and appended to the pod **after** rendering by `extend_pod_env`,
   which also appends every other gateway env var. The template therefore
   uses only `{{ kernel_id }}` and omits those three env entries; the pod
   command forwards the appended real values as explicit quoted CLI arguments
   to `launch_ipykernel.py` (verified 648 lines: it does not read them
   itself), plus `--cluster-type none`. `LOG_LEVEL`/`EG_LOG_LEVEL` are pinned
   to `"30"` because the launcher defaults to DEBUG (10), which can print
   channel connection material; the gateway runs `--log-level=WARNING`.
   Kernel and gateway logs are never collected, tailed, or uploaded.
6. **Two fresh kernels per proof run** — a BUILD kernel runs `build_task.py`
   (PptxGenJS 4.0.1 authors a one-slide deck) and streams the PPTX back over
   the same bounded framed transport; the client then kills it and requires
   HTTP 404 confirmation before starting a separate RENDER kernel. The render
   kernel receives the bounded deck inline (base64 inside the
   `execute_request` code, capped at a fixture constant; the render task
   enforces its own byte/base64 bounds and end-to-end SHA-256 continuity),
   reports `preexisting_deckpptx=false` **before** writing anything
   (fresh-pod evidence), renders via LibreOffice → PDF → Poppler PNG, and
   streams the PNG back. The client asserts distinct kernel UUIDs, digest
   continuity, PPTX zip magic, PNG signature/IHDR/CRC, and a full Pillow
   decode.
7. **Negative probes (all required, none skippable, snapshot-guarded)** —
   - client `KERNEL_IMAGE` override must be ignored: the live pod still runs
     the pinned image;
   - client `KERNEL_NAMESPACE=pptx-wrong` (claim delimitation below);
   - impersonated gateway-identity pod creation outside `pptx-jobs` must be
     denied `forbidden`, with an in-namespace positive control;
   - live pod invariant probe asserts by **name and boolean only** (never env
     values): no credential-shaped env names, no `valueFrom`, automount
     false, pinned image, non-root ids, read-only rootfs, dropped
     capabilities, emptyDir volumes, `LOG_LEVEL=30`, `component=kernel`.
    Authentication and namespace-tamper probes are bracketed by fail-closed,
    metadata-only all-namespace snapshots (namespace, name, UID). Authentication
    requires zero endpoint differences; namespace tampering permits differences
    only inside `pptx-jobs`. Pods created and removed between snapshots are not
    observed, so this is not a continuous zero-side-effect proof.
8. **Cancellation** — every client run kills its kernels via
   `DELETE /api/kernels/{id}`; the harness requires labeled pods to disappear
   within a bounded timeout.
9. **Always cleanup** — an EXIT trap deletes the namespace, destroys the kind
   cluster, removes local images, and unlinks the scoped kubeconfig and
   rendered gateway manifest (`rm` on the CI-ephemeral runner filesystem —
   accurate unlink, not a claim of secure erasure). The synthetic token is
   generated per run, never echoed, never committed, and never appears in
   results (booleans/counts/digests/dimensions only). No artifact upload
   steps exist in the workflow.

## Wrong-namespace semantics (explicit claim delimitation)

At the pinned revision, `K8sProcessProxy` trusts a client-supplied
`KERNEL_NAMESPACE` for status polling (`list_namespaced_pod`), while the
rendered template pins the literal namespace. A `KERNEL_NAMESPACE=pptx-wrong`
override therefore does **not** demonstrate caller-side input validation:
the failure mode is containment evidence — any created pod still lands in
`pptx-jobs` (literal template), and the proxy's polling of the wrong
namespace fails under the namespace-scoped Role. The client reports
`rejected=true` **only** for an explicit non-201 kernel POST status (recorded
in the result as `http_status`), taken only after an auth-positive control;
websocket/URL/timeout errors never count as rejection. A POST that is
accepted and then fails (or even starts) is a test failure, never laundered
into a rejection. No future production adapter authentication is claimed or
tested here.

## Wire protocol

jupyter-server 1.24.0 `services/kernels/handlers.py` `on_message` does
`json.loads(frame)` then `frame.pop('channel', None)` and reads
`frame['header']` as a dict, so the client sends and receives JSON **dicts**
(`header`, `parent_header`, `metadata`, `content`, `channel`, `buffers`) —
not ZMQ-style frame arrays. Received text is length-bounded before
`json.loads`, and unexpected binary frames are rejected. Documented
limitation: `websocket-client` allocates each incoming frame internally
before that bound can be applied, so the bound limits parsing and
reassembly, not the initial allocation.

## Pinned-rev upstream behaviors this design depends on

- `launch_kubernetes.py` loads the kernel-pod template from its own script
  directory, renders with jinja2, creates objects from the rendered body, and
  `extend_pod_env` runs **after** rendering, overwriting every templated env
  name present in the gateway process environment and then appending
  **every** gateway environment variable into the kernel pod. A template env
  list alone cannot prevent leakage; the gateway Deployment env allowlist is
  the isolation boundary. Gateway env beyond the synthetic
  `EG_AUTH_TOKEN`/`KG_AUTH_TOKEN` pair must never include provider, broker,
  or MCP credentials, because `remotemanager.py _launch_kernel` deletes only
  those two names after applying user overrides.
- Kernel status polling uses the `kernel_id` + `component=kernel` label
  selector and namespace-scoped list/delete; the worker service account has
  no bindings at all.
- KIP is not used; no runtime sockets; no cloud model credentials exist in
  this fixture's gateway; images are never pushed anywhere.

## Version island (fixture-only)

EG 3.3.0 requires `jupyter-client<7,>=6.1.12` and `pyzmq<25,>=20`;
ipykernel 6.30.1 needs jupyter-client>=8 and pyzmq>=25 and cannot co-install.
The fixture therefore uses one shared legacy venv per image: EG 3.3.0 +
ipykernel 6.29.5 + jupyter-client 6.1.12 + pyzmq 24.0.1 (+ pycryptodomex
3.20.0 for the launcher, whose imports are `Cryptodome` — the `-domex`
distribution, not `pycryptodome`), with kubernetes 31.0.0, jinja2 3.1.6
(3.1.4 is vulnerable and must not be pinned), pyyaml 6.0.3, requests 2.32.5,
websocket-client 1.8.0, Pillow 11.3.0 on the gateway/client side. Installs
use plain pinned `pip install pkg==version` — no `--no-deps`, no
`--ignore-requires-python` — so a real metadata conflict fails CI rather
than being bypassed. This island is chosen for least scope and is **not**
automatically approved for production.

Base image: `docker.io/library/node:22-bookworm-slim@sha256:43ac6c60…`
(Debian 12; linux/amd64 manifest digest
`25330af3531fb5e23318554a0aa911125b6e91b1b777edf7655501d207c067a2`),
selected so the distro python3.11 is compatible with the legacy pyzmq pin.

## Hermeticity and honest gaps

- apt packages are installed at build time from current Debian mirrors; no
  apt snapshot lock was supplied. The test image is **not** reproducible and
  is not released or published anywhere.
- npm transitive dependencies of pptxgenjs are not lockfile-pinned; pip
  transitives (jupyter-server 1.x, tornado, etc.) resolve freely within the
  declared constraints.
- kubectl currently uses `KUBECTL_SOURCE=runner_preinstalled` with a
  client/node skew gate; switch to `pinned_download` for hermetic runs.
- Group B pins were chosen for compatibility (parent registry-verified:
  pycryptodomex 3.20.0, kubernetes 31.0.0, pptxgenjs 4.0.1, jinja2 3.1.6);
  the remaining pins must be re-verified on PyPI/npm by the parent
  immediately before publish.
- Static unit tests strip whole-line comments before content assertions so
  rationale comments (which legitimately mention e.g. channel-connection
  secrets in prose) are never confused with payload; comments are not
  rewritten to satisfy checks.
- No historical/deck-authoring helpers are exercised in this stage; scope is
  a simple one-slide deck, fresh-kernel render, and transport proof.

## Parent verification checklist before publish

1. Remaining Group B pins exist on PyPI/npm at the exact versions in
   `pins.env` (jupyter-enterprise-gateway 3.3.0, jupyter-client 6.1.12,
   ipykernel 6.29.5, pyzmq 24.0.1, pyyaml 6.0.3, requests 2.32.5,
   websocket-client 1.8.0, Pillow 11.3.0).
2. `jupyter enterprisegateway` CLI accepts the flags used
   (`--ip --port --log-level --KernelSpecManager.allowed_kernelspecs`).
3. pptxgenjs 4.0.1 API surface used in `build_deck.js`.
4. Optional: pinned kubectl, npm lockfile, apt snapshot lock.

## Licensing

Upstream sources are consumed only from the pinned checkout
(`jupyter-server/enterprise_gateway`, BSD-3-Clause, `LICENSE.md` verified
present) via COPY in CI builds; `LICENSE.md` is copied into both images both
next to the copied launchers and inside the kernelspec directory, and
`render_check.py` asserts the launchers copy. No upstream files are forked
into this repository. `runtime/k8s/kernel-pod.yaml.j2`, the kernelspec patch,
the client, the probes, the worker tasks, and all tests are fixture-authored.

## How it runs

PRs touching only this workflow and this directory trigger
`presentation-qualification` (permissions `contents: read`, 30-minute
timeout, pinned actions/checkout @ `3d3c42e5…` v7.0.1 and
actions/setup-python @ `5fda3b95…` v7.0.0 with host Python 3.11). The static
job runs stdlib-only unit tests; the runtime job runs
`runtime/run_runtime_suite.sh`, which fails closed on any pending pin,
inconsistent pin combination, or unresolved dependency. Nothing is executed
against any live cluster, and no local execution is claimed — CI is the only
validation environment.
