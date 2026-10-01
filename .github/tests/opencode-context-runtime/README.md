# OpenCode context-only runtime probe

Test-owned fixture for `makeitworkcloud/charts`, maintained by makeitworkcloud / xnoto.
Its only consumer is `.github/workflows/opencode-context-runtime.yml` on pull requests.
It changes no chart content, image, production configuration, or GitOps selection.
No chart bump, publication, merge, or live operation is authorized by this fixture.

## Scope and evidence

The probe attempts actual host-dispatched context-mode calls in the unchanged
official OpenCode image, not direct invocation of plugin handlers. A local,
deterministic ChatCompletions responder supplies synthetic tool calls; it performs
no model inference and uses no provider account. Passing proves only the tested
behaviors. A failed or unexecuted required case fails the aggregate without waiver.

- Image: `ghcr.io/anomalyco/opencode:1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8`, Linux/amd64.
- Plugin: `context-mode@1.0.169` only; no opencode-mem or embedding service.
- Published tarball SHA-512: `94JIaFuLjF9SO2BsGTrbGtyT44K95+9OC8BdbaL/UT76xOkanJLfUR5CzmNw+GELXZQqH4nBrKg9wjBnSFkVnQ==`.
- The runner checks published manifest/version and selected compiled-file hashes
  against the installed package. Transitive npm dependencies remain nonhermetic.
- No standalone Node, Bun, Python, libc shim, or OS packages are added to the app.
  Features requiring additional interpreters are outside this probe's scope.

## Isolation and lifecycle

Python standard-library code on the hosted CI runner orchestrates Docker. Each run
has disposable HOME and separate configuration-overlay volumes and a UUID-named
internal Docker network. No production storage or credentials are mounted, and
the checkout mount contains only this test directory, read-only at `/probe`.
Both upstream storage overrides are explicit: `CONTEXT_MODE_DIR` selects the
server content root, while `CONTEXT_MODE_DATA_DIR` selects the adapter's parent
root. They align content and plugin-owned sessions under the same retained HOME
without moving OpenCode's separately seeded configuration directory.

The app runs as UID/GID 1000 with read-only root, all capabilities dropped,
no-new-privileges, disabled core dumps, and a bounded writable `/tmp` tmpfs.
A root helper has CHOWN only and changes ownership of fresh volume mountpoints;
a separate non-root helper seeds synthetic project/config files. Helpers use the
same stock image, not a new runtime image. No host environment is forwarded.

The responder binds only the internal bridge gateway on an ephemeral port; no
container ports are published. The cold app temporarily joins the ordinary bridge
for public package installation, then disconnects before any tool dispatch. The
runner asserts its only remaining network is internal. A positive external probe
on the ordinary bridge precedes a same-image internal-health/blocked-external
probe, so a broken shell/download client is not accepted as isolation evidence.
Warm replacement retains HOME but starts with fresh configuration on the internal
network only. This is synthetic container replacement, not Kubernetes recovery.

The explicit provider allowlist contains only `fixture`; its API marker is public
synthetic data. Global permissions deny by default, allowing the named probe tools.
`probe`/`other` are synthetic agents, `restricted` denies all, and `ask` requires
approval for `ctx_index`. Real production agent prompts are not loaded.

## Required cases

| Case | Required evidence |
| --- | --- |
| Artifact/registration | Published-file hashes match; index/search registered once; no memory tool |
| Index/search | Actual OpenCode ToolPart call ID, tool name, input and terminal state; recall includes both marker and indexed source, not just query echo |
| Malformed input | Content `42` yields a content/schema error for the attempted call |
| Restricted agent | A forced index call must not complete or index its forbidden marker |
| Host approval | A pending permission must match the session, tool and call ID before indexing; never grant it, abort instead |
| Plugin policies | Separate `.claude/settings.json` deny/ask shell policies block synthetic touch commands; both sentinels remain absent |
| Project boundary | Project B search completes without recalling project A's indexed source |
| Replacement | Same-session indexed content recalled after retained-HOME/fresh-config offline replacement |
| Content sharing | Other-agent content-store behavior is recorded, not described as user isolation |
| Resume boundary | Seed a synthetic raw prompt, compact through OpenCode, verify an unconsumed SessionDB snapshot contains the marker, then reject cross-agent system-prompt injection |
| Broken security | Synthetic throwing security bundle leaves tools registered but the actual index call errors with the fail-closed marker |
| Cleanup | Every tracked container, volume and network is removed |

Context-mode's own routing security is required with
`CONTEXT_MODE_REQUIRE_SECURITY=1`. The broken-bundle case points
`CONTEXT_MODE_SECURITY_BUNDLE_PATH` to the synthetic test module. Plugin policy
checks are distinct from OpenCode's native permission configuration. Generic
startup failure cannot pass either negative test. Synthetic SQLite inspection is
limited to the fixture's context databases; no OpenCode authentication store is read.

## Validation and reporting

The workflow uses read-only GitHub permissions and a SHA-pinned checkout without
persisted credentials, has no push or dispatch trigger, and uploads no artifacts.
CI runs syntax/unit checks and the runtime probe; no local validation is claimed.
The global runtime budget is 25 minutes within a 30-minute job limit. Cleanup has
one absolute deadline capped at three additional minutes, rather than a full
timeout per resource. It runs on normal exit, failure and handled termination
signals; cleanup failure is red. The host-approval case checks abort success,
waits for idle, and rechecks both the call and indexed marker before passing.
Native-deny evidence requires a working registry and allowed-agent index control;
deny-based tool hiding is recorded, not mistaken for a missing installation.
Approval and plugin-policy cases require offered-tool evidence; a successful
synthetic shell control precedes the plugin-policy negatives. Fixed diagnostic
markers distinguish installation and plugin-loading failures where reported.
Archive inspection selects the top-level package manifest, never a nested
dependency's manifest. Approval reports distinguish completed calls from terminal
errors without an approval prompt. An unavailable context database is unknown,
not proof of absent side effects; persistent/ephemeral location booleans aid
diagnosis without changing the expected persistence contract. Resume setup
failure remains red but does not suppress independent replacement/security cases.
Output is a selected JSON summary of statuses, fixed error categories, timings and
synthetic observation booleans, not raw logs, configuration, prompts or credentials.

No inference-quality, production privacy, complete interpreter support, ARM,
Kubernetes/PVC, HA, node-loss recovery or deployed-readiness guarantee follows.
The rejected Node-image/tooling-PVC redesign is not implemented.

## Source references

- [OpenCode session handlers](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/opencode/src/server/routes/instance/httpapi/handlers/session.ts) and [tool dispatch](https://github.com/anomalyco/opencode/blob/16747470f976aca3d362ad730bcd3fe82ecc2c9a/packages/opencode/src/session/tools.ts).
- Released context-mode [plugin](https://github.com/mksglu/context-mode/blob/589d8214d56740a28b5f7bf63167743d586b0b40/src/adapters/opencode/plugin.ts), [routing](https://github.com/mksglu/context-mode/blob/589d8214d56740a28b5f7bf63167743d586b0b40/hooks/core/routing.mjs), and [storage/resume](https://github.com/mksglu/context-mode/blob/589d8214d56740a28b5f7bf63167743d586b0b40/src/session/db.ts).

## Why a test-owned fixture

The existing memory probe (#113) exercises its localhost memory API, not
context-mode native host dispatch. The stopped init-runtime experiment (#120)
adds dependencies/gcompat and tests memory compatibility; resuming that design
is outside the approved unchanged-image scope. The official OpenCode experimental
API exposes tool listing, not a direct tool-execution endpoint. This fixture
therefore uses the maintained OpenCode session API and official OpenAI-compatible
SDK with a minimal deterministic test responder rather than a custom production
bridge or paid model service. Existing chart Helm/hygiene automation remains the
static validation surface. The new script/responder are explicitly test-owned and
maintained by makeitworkcloud / xnoto; approval is for this diagnostic PR, not
perpetual runtime enablement.
