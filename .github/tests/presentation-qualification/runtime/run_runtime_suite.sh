#!/usr/bin/env bash
# Presentation qualification — FIRST stage, CI-only core proof.
# Runs entirely inside a disposable, checksum-pinned kind cluster on the
# hosted runner (kind's default kindnet CNI; NetworkPolicy is NOT enforced,
# so network isolation is reported INCOMPLETE — a static, unqualified
# networkpolicy.yaml example is kept but never applied or claimed). Gates
# CORE scope: fixed-namespace RBAC, pod hardening, two-kernel build/render
# freshness, bounded transport, auth, cancellation, and label-independent
# all-namespace pod snapshots around every negative probe. The suite never
# collects kernel or gateway logs, never echoes credentials (shell tracing is
# not enabled), and uploads nothing.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$FIXTURE_DIR/../../.." && pwd)"
UPSTREAM_DIR="$REPO_ROOT/upstream-eg"

CLUSTER_NAME=pptx-qual
KIND_CONTEXT="kind-$CLUSTER_NAME"
NAMESPACE=pptx-jobs
WORKER_TAG=pptx-qual/worker:ci
GATEWAY_TAG=pptx-qual/gateway:ci
BASE_URL=http://127.0.0.1:8888

WORK_DIR="${RUNNER_TEMP:-/tmp/opencode/pptx-qualification/runner}/run"
umask 077
mkdir -p "$WORK_DIR/bin"
export KUBECONFIG="$WORK_DIR/kubeconfig"
KUBECTL_BIN=""

cleanup() {
  local rc=$?
  set +e
  if [[ -f "$WORK_DIR/portforward.pid" ]]; then
    kill "$(cat "$WORK_DIR/portforward.pid")" 2>/dev/null || true
  fi
  if [[ -n "$KUBECTL_BIN" && -x "$KUBECTL_BIN" && -f "$KUBECONFIG" ]]; then
    "$KUBECTL_BIN" --context "$KIND_CONTEXT" delete namespace "$NAMESPACE" --ignore-not-found --wait=false >/dev/null 2>&1 || true
  fi
  if [[ -x "$WORK_DIR/bin/kind" ]]; then
    "$WORK_DIR/bin/kind" delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
  fi
  docker rmi -f "$WORKER_TAG" "$GATEWAY_TAG" >/dev/null 2>&1 || true
  rm -f "$KUBECONFIG" "$WORK_DIR/gateway.yaml" "$WORK_DIR/deny.err" "$WORK_DIR/pf.log" "$WORK_DIR"/pods-*.json
  exit "$rc"
}
trap cleanup EXIT

fail() {
  echo "QUALIFICATION FAILURE: $*" >&2
  if [[ -n "$KUBECTL_BIN" && -x "$KUBECTL_BIN" && -f "$KUBECONFIG" ]]; then
    "$KUBECTL_BIN" --context "$KIND_CONTEXT" get events -n "$NAMESPACE" \
      -o jsonpath='{range .items[*]}{.reason}{"\n"}{end}' 2>/dev/null | sort | uniq -c | tail -n 10 >&2 || true
  fi
  exit 1
}

pods_snapshot() {
  local path=$1
  "$KUBECTL_BIN" --context "$KIND_CONTEXT" get pods -A \
    -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.metadata.uid}{"\n"}{end}' \
    > "$path" 2>/dev/null || fail "all-namespace pod snapshot failed"
}

assert_snapshots_clean() {
  local before=$1 after=$2 label=$3 mode=${4:-scope}
  python3 "$FIXTURE_DIR/runtime/client/snapshot_diff.py" "$before" "$after" "$NAMESPACE" "$mode" \
    || fail "pod scope escape detected by $label snapshot comparison"
}

cd "$FIXTURE_DIR"
python3 check_pins.py pins.env
set -a
. ./pins.env
set +a
: "${GITHUB_STEP_SUMMARY:=/dev/null}"

[[ -d "$UPSTREAM_DIR" ]] || fail "upstream checkout missing at $UPSTREAM_DIR"
for upstream_path in \
  etc/kernel-launchers/kubernetes/scripts/launch_kubernetes.py \
  etc/kernel-launchers/kubernetes/scripts/kernel-pod.yaml.j2 \
  etc/kernelspecs/python_kubernetes/kernel.json \
  etc/kernel-launchers/python/scripts/launch_ipykernel.py \
  LICENSE.md; do
  [[ -f "$UPSTREAM_DIR/$upstream_path" ]] || fail "missing pinned upstream file: $upstream_path"
done

curl -fsSL -o "$WORK_DIR/bin/kind" \
  "https://github.com/kubernetes-sigs/kind/releases/download/v${KIND_VERSION#v}/kind-linux-amd64"
echo "$KIND_SHA256  $WORK_DIR/bin/kind" | sha256sum -c - >/dev/null
chmod 0755 "$WORK_DIR/bin/kind"

if [[ "$KUBECTL_SOURCE" == "pinned_download" ]]; then
  curl -fsSL -o "$WORK_DIR/bin/kubectl" \
    "https://dl.k8s.io/release/v${KUBECTL_VERSION#v}/bin/linux/amd64/kubectl"
  echo "$KUBECTL_SHA256  $WORK_DIR/bin/kubectl" | sha256sum -c - >/dev/null
  chmod 0755 "$WORK_DIR/bin/kubectl"
  KUBECTL_BIN="$WORK_DIR/bin/kubectl"
else
  command -v kubectl >/dev/null 2>&1 || fail "runner kubectl missing; set KUBECTL_SOURCE=pinned_download with verified pins"
  KUBECTL_BIN="$(command -v kubectl)"
  node_minor="$(printf '%s' "$KIND_NODE_IMAGE" | sed -E 's|.*:v1\.([0-9]+)\..*|\1|')"
  client_json="$("$KUBECTL_BIN" version --client -o json || true)"
  printf '%s' "$client_json" | python3 -c '
import json
import sys

node_minor = int(sys.argv[1])
doc = json.load(sys.stdin)
version = doc["clientVersion"]
assert version["major"] == "1", "unexpected kubectl major %r" % version["major"]
skew = abs(int(version["minor"]) - node_minor)
assert skew <= 1, (
    "kubectl 1.%s skews more than one minor from kind node 1.%d; "
    "set KUBECTL_SOURCE=pinned_download with verified pins" % (version["minor"], node_minor)
)
print("kubectl skew gate ok: client 1.%s vs node 1.%d" % (version["minor"], node_minor))
' "$node_minor"
fi
export PATH="$WORK_DIR/bin:$PATH"

docker build --build-arg BASE_IMAGE="$NODE_BASE_IMAGE" \
  -f "$FIXTURE_DIR/runtime/images/worker.Dockerfile" -t "$WORKER_TAG" "$REPO_ROOT"
docker build --build-arg BASE_IMAGE="$NODE_BASE_IMAGE" --build-arg WORKER_IMAGE="$WORKER_TAG" \
  -f "$FIXTURE_DIR/runtime/images/gateway.Dockerfile" -t "$GATEWAY_TAG" "$REPO_ROOT"

"$WORK_DIR/bin/kind" create cluster --name "$CLUSTER_NAME" --image "$KIND_NODE_IMAGE" \
  --kubeconfig "$KUBECONFIG" --wait 180s
"$KUBECTL_BIN" --context "$KIND_CONTEXT" wait --for=condition=Ready node --all --timeout=300s
"$WORK_DIR/bin/kind" load docker-image "$WORKER_TAG" --name "$CLUSTER_NAME"
"$WORK_DIR/bin/kind" load docker-image "$GATEWAY_TAG" --name "$CLUSTER_NAME"

"$KUBECTL_BIN" --context "$KIND_CONTEXT" apply \
  -f "$FIXTURE_DIR/runtime/k8s/namespace.yaml" \
  -f "$FIXTURE_DIR/runtime/k8s/rbac.yaml"
PQ_TOKEN="$(openssl rand -hex 32)"
PQ_WRONG_TOKEN="$(openssl rand -hex 32)"
[[ "$PQ_WRONG_TOKEN" != "$PQ_TOKEN" ]] || fail "generated auth-negative token unexpectedly matched"
export PQ_TOKEN
sed -e "s|__PQ_TOKEN__|$PQ_TOKEN|" -e "s|__GATEWAY_IMAGE__|$GATEWAY_TAG|" \
  "$FIXTURE_DIR/runtime/k8s/gateway.yaml.in" > "$WORK_DIR/gateway.yaml"
"$KUBECTL_BIN" --context "$KIND_CONTEXT" apply -f "$WORK_DIR/gateway.yaml"
"$KUBECTL_BIN" --context "$KIND_CONTEXT" -n "$NAMESPACE" rollout status deployment/pptx-qual-gateway --timeout=240s

"$KUBECTL_BIN" --context "$KIND_CONTEXT" -n "$NAMESPACE" port-forward svc/pptx-qual-gateway \
  --address 127.0.0.1 8888:8888 >"$WORK_DIR/pf.log" 2>&1 &
echo $! > "$WORK_DIR/portforward.pid"

ready=""
last_ready_code=""
for _ in $(seq 1 60); do
  code=$(curl -s --connect-timeout 3 --max-time 5 -o /dev/null -w '%{http_code}' \
    -H "Authorization: token $PQ_TOKEN" "$BASE_URL/api/kernelspecs" || true)
  if [[ "$code" =~ ^[0-9]{3}$ ]]; then last_ready_code=$code; else last_ready_code=none; fi
  if [[ "$code" == "200" ]]; then ready=1; break; fi
  sleep 5
done
if [[ -z "$ready" ]]; then
  pf_alive=false
  if [[ -f "$WORK_DIR/portforward.pid" ]] && kill -0 "$(cat "$WORK_DIR/portforward.pid")" 2>/dev/null; then
    pf_alive=true
  fi
  # Deliberately project status fields only; never collect pod specs, messages,
  # environment, logs, or raw port-forward/curl output for readiness diagnosis.
  gateway_status=$("$KUBECTL_BIN" --context "$KIND_CONTEXT" -n "$NAMESPACE" \
    get pods -l app=pptx-qual-gateway \
    -o 'jsonpath={range .items[*]}{.status.phase}{"|"}{range .status.containerStatuses[*]}{.restartCount}{":"}{.state.waiting.reason}{":"}{.lastState.terminated.reason}{":"}{.lastState.terminated.exitCode}{","}{end}{"\n"}{end}' \
    2>/dev/null || true)
  python3 - "$last_ready_code" "$pf_alive" "$gateway_status" <<'PY'
import re
import sys

http_code = sys.argv[1] if re.fullmatch(r"[0-9]{3}", sys.argv[1]) else "none"
print("READINESS_DIAGNOSTIC http_status=%s portforward_alive=%s" % (http_code, sys.argv[2]))
for row in sys.argv[3].splitlines():
    fields = row.split("|", 1)
    phase = re.sub(r"[^A-Za-z0-9]", "", fields[0]) or "unknown"
    print("READINESS_DIAGNOSTIC pod_phase=%s" % phase)
    if len(fields) == 1:
        continue
    for status in fields[1].split(","):
        if not status:
            continue
        restart, waiting, terminated, exit_code = (status.split(":") + [""] * 4)[:4]
        restart = restart if restart.isdigit() else "unknown"
        waiting = re.sub(r"[^A-Za-z0-9]", "", waiting) or "none"
        terminated = re.sub(r"[^A-Za-z0-9]", "", terminated) or "none"
        exit_code = exit_code if exit_code.isdigit() else "none"
        print("READINESS_DIAGNOSTIC restart_count=%s waiting_reason=%s terminated_reason=%s terminated_exit_code=%s" % (restart, waiting, terminated, exit_code))
PY
  fail "gateway API never became ready (diagnostic only; no readiness cause inferred)"
fi

pods_snapshot "$WORK_DIR/pods-auth-before.json"
unauth=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/kernelspecs" || true)
badtok=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: token $PQ_WRONG_TOKEN" "$BASE_URL/api/kernelspecs" || true)
unauth_post=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  --data '{"name":"presentation","env":{}}' "$BASE_URL/api/kernels" || true)
badtok_post=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -H "Authorization: token $PQ_WRONG_TOKEN" \
  --data '{"name":"presentation","env":{}}' "$BASE_URL/api/kernels" || true)
[[ "$unauth" =~ ^(401|403)$ ]] || fail "unauthenticated GET accepted (http $unauth)"
[[ "$badtok" =~ ^(401|403)$ ]] || fail "wrong token GET accepted (http $badtok)"
[[ "$unauth_post" =~ ^(401|403)$ ]] || fail "unauthenticated kernel POST accepted (http $unauth_post)"
[[ "$badtok_post" =~ ^(401|403)$ ]] || fail "wrong token kernel POST accepted (http $badtok_post)"
pods_snapshot "$WORK_DIR/pods-auth-after.json"
assert_snapshots_clean "$WORK_DIR/pods-auth-before.json" "$WORK_DIR/pods-auth-after.json" "auth-negative" zero

run_client() {
  local mode=$1
  shift
  docker run --rm --network host \
    -e PQ_TOKEN -e PQ_BASE_URL="$BASE_URL" -e PQ_KERNEL_NAME=presentation -e PQ_WORKER_IMAGE="$WORKER_TAG" \
    -v "$FIXTURE_DIR":/fixture:ro -v "$WORK_DIR":/out \
    "$GATEWAY_TAG" python /fixture/runtime/client/client.py --mode "$mode" --out "/out/result-$mode.json" "$@"
}

wait_for_kernel_pod_and_assert() {
  local client_pid=$1
  local deadline=$(( SECONDS + 240 ))
  while (( SECONDS < deadline )); do
    if ! kill -0 "$client_pid" 2>/dev/null; then return 2; fi
    if ("$KUBECTL_BIN" --context "$KIND_CONTEXT" -n "$NAMESPACE" get pods -l app=pptx-qualification-kernel --no-headers 2>/dev/null || true) | grep -q Running; then
      ("$KUBECTL_BIN" --context "$KIND_CONTEXT" -n "$NAMESPACE" get pods -l app=pptx-qualification-kernel -o json 2>/dev/null || true) \
        | python3 "$FIXTURE_DIR/runtime/client/probe_pod_invariants.py" "$NAMESPACE" "$WORKER_TAG" \
        || fail "live kernel pod invariants violated"
      return 0
    fi
    sleep 3
  done
  return 1
}

pods_snapshot "$WORK_DIR/pods-ns-before.json"
set +e
run_client start-expect-failure --set-env KERNEL_NAMESPACE=pptx-wrong --timeout 200
client_rc=$?
set -e
[[ $client_rc -eq 0 ]] || fail "KERNEL_NAMESPACE probe failed (client rc=$client_rc)"
python3 - "$WORK_DIR/result-start-expect-failure.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    result = json.load(handle)
assert result.get("ok") is True, result
assert result.get("rejected") is True, result
status = result.get("http_status")
assert isinstance(status, int) and status != 201, status
print("NAMESPACE_OVERRIDE_REJECTED http=%d" % status)
PY
pods_snapshot "$WORK_DIR/pods-ns-after.json"
assert_snapshots_clean "$WORK_DIR/pods-ns-before.json" "$WORK_DIR/pods-ns-after.json" "namespace-tamper"
"$KUBECTL_BIN" --context "$KIND_CONTEXT" -n "$NAMESPACE" delete pods -l app=pptx-qualification-kernel \
  --ignore-not-found --wait=false >/dev/null 2>&1 || true

set +e
run_client full --timeout 420 &
FULL_PID=$!
set -e
wait_for_kernel_pod_and_assert "$FULL_PID" || fail "no running kernel pod observed during full run"
wait "$FULL_PID" || fail "full qualification client run failed"
python3 - "$WORK_DIR/result-full.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    result = json.load(handle)
assert result.get("ok") is True, "client reported failure"
for key in (
    "pptx_signature_ok",
    "png_decoded",
    "distinct_kernel_ids",
    "build_kernel_terminated",
):
    assert result.get(key) is True, key
assert result.get("preexisting_deck") is False, result.get("preexisting_deck")
assert result.get("render_digest_ok") is True, result.get("render_digest_ok")
assert result["build_exit_code"] == 0, result["build_exit_code"]
assert result["render_exit_code"] == 0, result["render_exit_code"]
ihdr = result["png_ihdr"]
assert ihdr["width"] > 0 and ihdr["height"] > 0, ihdr
assert result["png_decoded_size"] == [ihdr["width"], ihdr["height"]], result["png_decoded_size"]
assert len(result["pptx_sha256"]) == 64 and len(result["png_sha256"]) == 64
assert result["pptx_bytes"] > 1000, result["pptx_bytes"]
assert result["pptx_chunks"] >= 1 and result["png_chunks"] >= 1
print("RESULT_FULL_OK")
PY
"$KUBECTL_BIN" --context "$KIND_CONTEXT" -n "$NAMESPACE" wait --for=delete pod -l app=pptx-qualification-kernel \
  --timeout=180s || fail "kernel pods were not removed after kernel kills"

set +e
run_client start-wait-kill --set-env KERNEL_IMAGE=pptx-qual/evil:ci --hold 40 --timeout 300 &
TAMPER_PID=$!
set -e
wait_for_kernel_pod_and_assert "$TAMPER_PID" || fail "no kernel pod observed during image-tamper run"
wait "$TAMPER_PID" || fail "image-tamper client run failed"
python3 - "$WORK_DIR/result-start-wait-kill.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    result = json.load(handle)
assert result.get("ok") is True and result.get("started") is True, result
print("IMAGE_OVERRIDE_IGNORED_KERNEL_STARTED")
PY
"$KUBECTL_BIN" --context "$KIND_CONTEXT" -n "$NAMESPACE" wait --for=delete pod -l app=pptx-qualification-kernel \
  --timeout=180s || fail "kernel pod was not removed after tamper-run kill"

PROBE_OVERRIDES='{"spec":{"automountServiceAccountToken":false}}'
set +e
"$KUBECTL_BIN" --context "$KIND_CONTEXT" --as=system:serviceaccount:pptx-jobs:pptx-gateway \
  -n default run pg-deny-probe --image="$WORKER_TAG" --restart=Never \
  --overrides="$PROBE_OVERRIDES" --command -- sleep 2 >/dev/null 2>"$WORK_DIR/deny.err"
deny_rc=$?
set -e
if [[ $deny_rc -eq 0 ]]; then
  "$KUBECTL_BIN" --context "$KIND_CONTEXT" -n default delete pod pg-deny-probe --ignore-not-found >/dev/null 2>&1 || true
  fail "gateway service account created a pod outside $NAMESPACE"
fi
grep -qi forbidden "$WORK_DIR/deny.err" || fail "RBAC denial probe failed for an unexpected reason"

set +e
"$KUBECTL_BIN" --context "$KIND_CONTEXT" --as=system:serviceaccount:pptx-jobs:pptx-gateway \
  -n "$NAMESPACE" run pg-allow-probe --image="$WORKER_TAG" --restart=Never \
  --overrides="$PROBE_OVERRIDES" --command -- sleep 4 >/dev/null 2>&1
allow_rc=$?
set -e
[[ $allow_rc -eq 0 ]] || fail "RBAC positive control failed: gateway SA cannot create a pod in $NAMESPACE"
"$KUBECTL_BIN" --context "$KIND_CONTEXT" --as=system:serviceaccount:pptx-jobs:pptx-gateway \
  -n "$NAMESPACE" delete pod pg-allow-probe --ignore-not-found --wait=true >/dev/null 2>&1 || true

CORE_STATUS=PASS
NETWORK_STATUS=INCOMPLETE
NETWORK_REASON="kind default CNI (kindnet) does not enforce NetworkPolicy; runtime/k8s/networkpolicy.yaml is a static, unqualified example that is never applied by this fixture"
OVERALL_STATUS=INCOMPLETE
python3 - "$WORK_DIR/qualification-status.json" "$CORE_STATUS" "$NETWORK_STATUS" "$OVERALL_STATUS" "$NETWORK_REASON" <<'PY'
import json
import sys

path, core, network, overall, reason = sys.argv[1:6]
doc = {
    "core_rbac_render_transport": core,
    "network_isolation": network,
    "network_reason": reason,
    "overall": overall,
    "note": "CI disposable cluster only; production qualification remains a parent decision",
}
with open(path, "w") as handle:
    json.dump(doc, handle, indent=2, sort_keys=True)
PY
{
  echo "### Presentation qualification (FIRST stage, CI-only)"
  echo "- core (fixed-namespace RBAC, pod hardening, fresh build+render kernels, bounded transport, auth, cancellation): $CORE_STATUS"
  echo "- network isolation: $NETWORK_STATUS — $NETWORK_REASON"
  echo "- overall: $OVERALL_STATUS (this workflow gates core scope only)"
  echo "- disposable kind cluster deleted; images never pushed; no artifacts uploaded"
} >> "$GITHUB_STEP_SUMMARY"

echo "QUALIFICATION_CORE=$CORE_STATUS"
echo "QUALIFICATION_NETWORK_ISOLATION=$NETWORK_STATUS ($NETWORK_REASON)"
echo "QUALIFICATION_OVERALL=$OVERALL_STATUS"
[[ "$CORE_STATUS" == "PASS" ]] || fail "core scope failed"
exit 0
