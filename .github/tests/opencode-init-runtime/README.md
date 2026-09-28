# Init Runtime Feasibility

Owner: makeitworkcloud. Isolated prototype, not chart adoption or release approval.
The PR-only workflow uses hosted Docker and the unchanged upstream
`ghcr.io/anomalyco/opencode:1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8`
on linux/amd64. No Dockerfile, image build, image push, registry login, custom
ONNX/glibc, provider fallback, production mount, or cluster operation exists.

## Lifecycle and Gate

One root init helper extracts official packages into a UUID runtime volume,
using the stock image's trusted public apk keys and strictly matched Alpine
3.24 repositories. Node >=22.13, gcompat, libgcc/libstdc++ and apk-resolved
dependencies are prepared once. Binutils lives in a separate inspection volume,
never the application. Applications mount runtime dependencies read-only.

A uses PATH and LD_LIBRARY_PATH only. B adds
`LD_PRELOAD=/opt/runtime/lib/libgcompat.so.0`. Both use distinct fresh UUID HOME
volumes; application paths are identical. Each has its own 15-minute budget and
B runs even if A fails. Common provisioning failure prevents both and is red.
Control A is evidence, never the gate. Green requires B's complete cold and warm
sequence AND successful cleanup. Any B failure ends this experiment.

Applications retain the upstream entrypoint, use numeric UID/GID 1000, read-only
rootfs, dropped capabilities and no-new-privileges. HOME/config/tmp are writable;
no host ports are published. Test-owned root helpers have only CHOWN added and
repair permissions only on fresh volumes, not persisted warm HOME trees.

OpenCode automatically installs context-mode@1.0.169 and opencode-mem@2.26.0
under HOME/.cache/opencode/packages/<spec>/node_modules/<name>, with lifecycle
scripts disabled by its upstream loader. No external npm install is added.
Provider list is empty, permissions deny, MCP empty, capture/extraction,
chat/compaction injection and profile features disabled. Context storage lives
under HOME/.local/share/context-mode. API authentication is a public synthetic
fixture, not a credential. Cold egress is needed for public packages/models;
this is not an egress allowlist or a malicious-dependency sandbox.

Readiness requires exact configured plugins and native tool registration, not
context tool dispatch. B must create one synthetic memory through the real
localhost API and recall identical id/content with finite similarity >=0.6.
HTTP 200 with success=false fails. It then stops/removes the application,
discards config/tmp, seeds a fresh config volume, and starts the same stock image
with retained HOME/deps and network=none. The same memory must be recalled.
No model inference request to an LLM, custom plugin bridge, or remote provider is
used; the memory path does execute the default local CPU embedding model.

## Evidence and Limits

CI reports exact installed apk name/version pairs via
`apk list --installed --manifest`, skipped package script names when the apk
database exposes a script archive, provisioning/bootstrap/write/recall timings,
OpenCode and Node PT_INTERP, gcompat dynamic __vsnprintf_chk export, ONNX
DT_NEEDED, actual PID 1 gcompat mapping, security and Node SQLite FTS5 checks,
and detected absolute/broken dependency symlinks. No symlink, interpreter or
resource-path relocation is performed. A loader stub named by DT_NEEDED may not
be a loadable ELF library; presence or symbol export is not compatibility proof.
First-write latency includes remaining background model warmup, not just compute.
No warm success/timing is claimed when cold write fails.

`--no-scripts` is deliberate fresh binary/library extraction, not a complete
bootable alternate root. Official 3.24 gcompat has no install hooks; Node's
post-upgrade script only warns about obsolete npm. Runtime dependencies may have
additional hooks; extraction success is not proof those are unnecessary. Actual
Node/native API execution is the gate; missing setup ends the experiment rather
than adding trust bypasses, chroot escapes, or undocumented relocation fixes.
See [apk options](https://github.com/alpinelinux/apk-tools/blob/master/doc/apk.8.scd),
[gcompat](https://github.com/alpinelinux/aports/blob/3.24-stable/main/gcompat/APKBUILD),
and [Node hook](https://github.com/alpinelinux/aports/blob/3.24-stable/main/nodejs/nodejs.post-upgrade).

Package revisions/transitive npm ranges and model revision are not frozen.
Cold dependency resolution is not hermetic. Offline replacement tests reuse,
not cache immutability, Kubernetes storage, ARM64, concurrency, DR, context host
dispatch, real conversation learning, or production safety. No raw maps, auth
files, response bodies or log dumps are printed; only fixed diagnostic markers,
symbol names and bounded sanitized command/HTTP error fields are emitted.

API/helper provenance: charts PR 113 at a34d8ef1646470c5d24275660c72d314f63b617b;
images PR 58 at 4aa256927c02577f253b2cbb8a09652c021e99ff. Prior run 36366947984
failed first write on __vsnprintf_chk; it is not a passing baseline. CI is the
only validation environment. Parent reviews/opens the PR; no dispatch/rerun,
merge, publication, chart bump, GitOps rollout or production changes are implied.
