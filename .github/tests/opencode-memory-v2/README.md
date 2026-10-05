# opencode-memory-v2 — CI runtime fixture (test-only)

Maintainers: `makeitworkcloud/xnoto` · Branch `test/opencode-memory-v2-runtime`
(from charts `main` @ `2f5d497c72763d38fe9e7cfdabab1eabec6264a9`) · The
historical `#113` fixture files are untouched; this adds a new, separate
fixture.

## Why this owned fixture exists

Upstream `opencode-mem` validation targets Ubuntu/Windows/macOS package setups;
the chart's existing checks cover Helm configuration. Neither exercises the **stock
`ghcr.io/anomalyco/opencode` container** (Alpine/musl, non-root UID 1000,
read-only rootfs, dropped capabilities, no published ports, offline restart).
This fixture covers exactly that gap, with synthetic data on a disposable CI
runner only.

## What a PASS means (scope)

- The pinned image serves `GET /api/info` with `version == "2.0.22"`.
- `GET /api/plugin?location[directory]=/home/opencode` returns a `location`
  envelope whose `directory` is exactly `/home/opencode`, and a plugin entry
  with id exactly `opencode-mem`, `source.type == "package"`, target exactly
  `opencode-mem@2.28.3` (or package target + resolved version `2.28.3`), and
  `state.status == "active"`. List presence, wrong id/target/version, or a
  `failed` state is rejected.
- Exactly one synthetic `POST /api/memories` with body
  `{"content": <synthetic text>, "containerTag": "sm_project_0c1f1a2b3c4d5e6f"}`
  (both fields required by the maintained API) returns `success === true`
  (strict; `1`/missing/`null` rejected) and a non-empty string `data.id`.
  The POST gets a dedicated ≤600 s budget (cold model download) and is never
  retried.
- `GET /api/search?q=...&tag=<encoded containerTag>&page=1&pageSize=10`
  returns `success === true` and `data.items` containing the exact id with
  `type == "memory"`, byte-identical `content`, and a finite numeric
  `similarity` ≥ 0.6 (lower bound only; no unsupported upper bound, no
  alternative score keys).
- After a graceful stop+remove, an **offline** (`--network none`) replacement —
  same image, same `--workdir /home/opencode`, same env, same persistent home
  volume, **new freshly seeded config volume** — reproduces the same recall
  with no further POST.
- `PASS` is printed (and exit code 0 returned) only when the lifecycle **and**
  scoped cleanup both succeeded.

**A PASS does NOT mean:** memory capture/native OpenCode tool dispatch,
permissions beyond the deny-all fixture config, LLM/provider behavior,
Kubernetes/Helm deployment, ARM, DR, or production-deployment acceptance.
Deliberately non-hermetic: the primary container performs cold public npm and
embedding-model downloads, and the plugin's transitive dependencies are not
pinned or verified (top-level pins only); the replacement proves the cached,
offline path.

## Pinned inputs

| Input | Value |
| --- | --- |
| Image | `ghcr.io/anomalyco/opencode:2.0.22@sha256:11f2b6c96d380867387fbee390c06cb47efffd9fdc37009b4cd40795b45dad19` (linux/amd64; `Dockerfile` at the vendor commit sets `ENTRYPOINT ["opencode"]`) |
| Plugin | `opencode-mem@2.28.3`, release `a24d79e34857aed9c5e708f5325714e6948bbfa7`; npm integrity `sha512-tIGQDODg9Taury02WbDYpNiKGOjwg5rudZADBxHR1FqDZYIjKmd8f77ZXLmfGSQYuPXIBK+jJG4u5yKLYvy2Gw==` |
| Vendor source | opencode `527f0b931d1f9b3ebd34e106c51b31ce5db5b075`: `packages/server/src/handlers/plugin.ts`, `packages/server/src/auth.ts`, `packages/cli/src/env.ts`, `packages/server/src/middleware/authorization.ts`, protocol groups `plugin.ts`/`location.ts`, `Dockerfile` |
| Plugin source | `src/config.ts`, `src/services/web-server.ts`, and **`src/services/api-handlers.ts`** (authoritative: `handleAddMemory` requires `content` + `containerTag`, returns `success:true, data.id`; `handleSearch(query, tag, page, pageSize)` returns `success:true, data.items:[{type:'memory', id, content, similarity}]`) plus `src/services/memory-scope.ts` (project-scope `sm_project_<hash>` containerTag shape) — all at the release above |
| API spec | https://opencode.ai/v2/openapi.json |

## Flow (`runtime.py`)

1. Global deadline (~22 min vs the 30-min job timeout) starts **before** the
   pull; every docker operation is bounded by `min(requested, remaining)` so a
   slow pull consumes — never exceeds — the overall budget. Diagnostics and
    cleanup run on separate budgets (≤5 min combined), reserving three job
    minutes for checkout, unit tests, and reporting. Readiness loops check
   the deadline before probing and before sleeping, and a success arriving
   after the deadline is rejected.
2. Pull + inspect with `--platform linux/amd64`: platform, `.Id`,
   `RepoDigests` only — never `Config.Env`.
3. UUID-named resources are tracked **before** creation, so a docker CLI
   timeout cannot orphan them; removal attempts `rm -f` even when `stop`
   fails, and existence is probed with explicit `container`/`volume` inspect
   kinds. Two seed files are generated world-readable (0755/0644) because the
   capability-less root preparer cannot traverse a 0700 tempfile dir:
   `opencode.json` (native `plugins`, `enabled_providers: []` — V1-compatible
    disable normalized by the pinned OpenCode source — and
   deny-all `permissions`) and `opencode-mem.jsonc` (absolute
   `storagePath: /home/opencode/.opencode-mem` inside the persistent home
   volume, pinned defaults, public fixture `webServerApiToken` on
   127.0.0.1:4747; no provider/model/API keys; `userProfileAnalysisInterval`
   absent).
4. A named root preparer (same image, UID 0, `--cap-drop ALL --cap-add CHOWN`,
   `--network none`, read-only, tiny seed dir mounted read-only) seeds each
   fresh config volume; it uses `--entrypoint sh` (image entrypoint is
   `opencode`) and orders `chmod` before `chown` (after chown, root no longer
   owns the files and `chmod` would need the dropped `CAP_FOWNER`). The
   replacement preparer touches only the new config volume — the retained home
   volume is not even mounted.
5. App container: `--platform linux/amd64`, `--user 1000:1000 --read-only
   --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp --workdir
   /home/opencode`, no published ports, no docker socket or checkout mounts;
   mounts are only the persistent home volume, the seeded writable config
   volume, and a tiny read-only bind of the generated `opencode.json`. Env is
   an explicit allow-list (`HOME`, XDG dirs, `OPENCODE_DB=opencode.db` — a
   bare filename resolved inside the XDG data dir under the persistent home,
   the canonical retained location — and `OPENCODE_PASSWORD`, the only
   credential, a public synthetic value enabling Basic `opencode` on `/api/*`).
   Command: `opencode serve --hostname 127.0.0.1 --port 4096`.
6. Security verification reads only selected inspect fields (user,
   read-only rootfs, `CapDrop == ["ALL"]`, `CapAdd` null/empty,
   no-new-privileges, empty port bindings, network mode) plus an in-container
   `id -u` == 1000.
7. Readiness (`/api/info`), registration (`/api/plugin`), and plugin web
    health (`/api/health`, `success === true` strictly) are distinct bounded
    stages; retry loops issue read-only GETs only — the POST is never replayed.
    A source-matched `failed` plugin state is terminal even if loading failed
    before its ID became available. Missing entries report only bounded
    identity/source/status fields; deadline errors retain the last sanitized
    failure. An active entry without the exact ID still cannot pass.
   All in-container HTTP uses stock `wget` via `docker exec` (10 s for GETs,
   ≤600 s for the single POST, exec timeout = wget budget + margin) with the
   Bearer fixture token for the plugin web API.
8. One synthetic POST + exact id/type/content/similarity search; graceful
   stop + remove; offline replacement with a **new** seeded config volume and
   the same home volume; identical recall asserted; exactly-one-POST enforced
   (`http.posts == 1`).
9. Scoped cleanup always runs — even after global-deadline exhaustion — on its
   own budget; cleanup failures fail the gate (no false PASS). Failure
   diagnostics merge stdout+stderr from `docker logs`, keep only
   allow-listed failure-signal lines, sanitize credential-like content, and
   clip to a bounded tail; no raw logs, nothing uploaded, no caches/artifacts.

Fixture credentials are public synthetic values; no production auth material
is used or mirrored.

## Failure stages

`startup` (image/platform/run/security/readiness/deadline) · `transport`
(docker CLI/exec/HTTP) · `registration` (plugin missing/failed/wrong
id/target/version, location mismatch) · `storage` (add/search id, type, or
content mismatch, duplicate POST) · `embedding` (similarity missing,
non-numeric, NaN, bool, or below 0.6) · `cleanup`.

## Tests

`test_runtime.py` (stdlib `unittest`, mocked docker/time) covers
malformed/wrapped/failed-state/wrong-id-target-version payloads, location
envelope exactness, strict `success is True` (rejecting `1`/missing),
`type == 'memory'`, similarity-only (no score fallback, no upper bound),
id/content/NaN/bool/threshold assertions, deadline behavior (pre-check,
delayed-success rejection, slow-pull budget, exhausted budget, separate
cleanup budget), cleanup semantics (stop failure still removes, rm failure
fails, explicit inspect kinds, track-before-create), sanitizer, diagnostics
filtering, single-POST enforcement with `containerTag`, seed-file modes, env
allow-list, and same workdir/env for both containers. CI is authoritative; the
fixture is not run locally.

## Repo impact

Test-only diff: the canonical changed-chart selector (first path components
intersecting directories with a direct `Chart.yaml`) yields `[]` ⇒
`packages/updater` is skipped, no chart version bump, `charts/` unchanged.
The workflow pins `actions/checkout` v7.0.1 to the verified full 40-character
commit `3d3c42e5aac5ba805825da76410c181273ba90b1`.

## Source references

- [OpenCode plugin API](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/protocol/src/groups/plugin.ts)
- [OpenCode Basic authentication](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/server/src/middleware/authorization.ts)
- [OpenCode legacy provider normalization](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/core/src/config/normalize.ts)
- [OpenCode database path resolution](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/core/src/database/database.ts)
- [Plugin memory API handlers](https://github.com/tickernelz/opencode-mem/blob/a24d79e34857aed9c5e708f5325714e6948bbfa7/src/services/api-handlers.ts)
- [Plugin scope-tag parser](https://github.com/tickernelz/opencode-mem/blob/a24d79e34857aed9c5e708f5325714e6948bbfa7/src/services/memory-scope.ts)
