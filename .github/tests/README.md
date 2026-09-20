# opencode-memory runtime probe

`opencode_memory_runtime.py` is a validation-only CI gate for the
opencode-memory local-embedding runtime. It runs on pull requests that touch
this test surface or `opencode-server/**` via the `opencode-memory-runtime`
workflow, and manually via workflow dispatch. This directory is test
documentation outside the chart tree; it is not a chart or release artifact.

- Pinned runtime: `ghcr.io/anomalyco/opencode:1.18.29` by digest and
  `opencode-mem@2.26.0` at release `0c8ed7d54382d9225def8484d691182d46e8552d`.
- Not hermetic: transitive npm dependencies and the local embedding model
  artifact are resolved at run time from public registries.
- A failing run is gate evidence for our rollout decision on the
  opencode-memory pilot; repository branch protection is not modified by this
  test.
- No paid inference (`enabled_providers` empty, global deny permission) and
  no provider, cluster, or OAuth credentials are read or forwarded. The web
  server token is a public synthetic fixture (`ci-fixture-not-a-secret`).
