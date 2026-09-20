# opencode-memory runtime probe

`opencode_memory_runtime.py` is a validation-only CI gate for the
opencode-memory local-embedding runtime. It runs on pull requests that touch
this test surface or `opencode-server/**` via the `opencode-memory-runtime`
workflow, and manually via workflow dispatch. This directory is test
documentation outside the chart tree; it is not a chart or release artifact.

- Pinned runtime: `ghcr.io/anomalyco/opencode:1.18.29` by digest and
  `opencode-mem@2.26.0` at release `0c8ed7d54382d9225def8484d691182d46e8552d`.
  The image is pulled for `linux/amd64` and its identity (config id, repo
  digests, architecture, OS) is asserted before use; mismatches fail with no
  fallback.
- Not hermetic: transitive npm dependencies and the local embedding model
  artifact are resolved at run time from public registries.
- Scope of a PASS: the plugin web API is enabled for this CI probe and
  capture/learning is disabled. Success proves only local embedding
  execution, API storage/retrieval, and persistence across a same-volume
  container replacement. It does NOT prove LLM capture/provider behavior,
  Kubernetes Service/PVC wiring, or production Secret wiring.
- A failing run is gate evidence for our rollout decision on the
  opencode-memory pilot; repository branch protection is not modified by this
  test.
- No paid inference (`enabled_providers` empty, global deny permission) and
  no provider, cluster, or OAuth credentials are read or forwarded. The web
  server token is a public synthetic fixture (`ci-fixture-not-a-secret`).

Maintainer: makeitworkcloud. Repo owner: Steven Welch (xnoto). Added per the
owner-approved rollout validation request in the committing conversation.
This is a test-only reusable artifact; it produces no runtime configuration.

Alternatives considered: the repository's existing Helm tests are static and
do not execute the image; the upstream plugin's Node/package tests do not run
against the exact OpenCode Alpine image; this probe reuses the plugin's
existing REST API with existing Docker and Python stdlib tooling, adding no
custom image and no new service.
