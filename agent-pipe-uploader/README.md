# Agent Pipe uploader chart

Owns the existing internal Deployment and ClusterIP Service at
`http://agent-pipe-uploader.opencode.svc:8080/mcp`. Namespace and
`opencode-artifacts` PVC remain cluster-owned. No AWS credentials, Kubernetes
token, TunnelBinding or OpenCode home mount. The artifact PVC is read-write.

## Profiles

| Profile | Operations | Exact hosts | Prefix | Limit |
| --- | --- | --- | --- | --- |
| agent-pipe | upload, download, verify | agent-pipe.s3.amazonaws.com, agent-pipe.s3.us-west-2.amazonaws.com | /deliveries/ | 100 MiB |
| agent-presentations | upload, download, verify | same bucket and hosts | /presentations/ | 100 MiB |
| slidespeak-exports | download, verify only | slidespeak-files.s3.amazonaws.com, slidespeak-files.s3.us-east-2.amazonaws.com | / | 100 MiB |

All profiles require unique nonempty SigV4 Algorithm, Credential, Date, Expires,
SignedHeaders and Signature query fields (each with `X-Amz-` prefix). Preserve
URLs unchanged; no redirects, wildcard hosts or signature rewriting. Optional
session tokens remain intact. New images reject missing/disallowed operations;
old images ignore the field and must not serve the vendor profile.

The helper exposes inspect, upload, download, full-response verify and
`remove_artifact(artifact, expected_sha256)`. Full reads return bytes/SHA-256;
HEAD/ETag is not verification. Removal is exact-local-regular-file only, no
symlinks/directories or S3 deletion, separately approved after stored verification
and return of the durable reference. Transfer prompts remain required. The helper
does not log/return signed URLs or body bytes; client output policy separately
permits tested S3 GET and explicit temporary tool-returned vendor GET links,
never PUT URLs or durable signed-URL records.

## Blocking release gate

Version 0.3.0 uses UNPUBLISHED source SHA
`63ccfde32e70decf81255e816cd2ada57b4f7e10` as a staging-only placeholder.
DO NOT MERGE OR DEPLOY until replaced with a verified main-published immutable
image SHA/digest and publication/registry evidence. Squash merge changes the
source SHA; never substitute `latest`. Render tests check shape, not publication.

Confirm applied private prefix/IAM/lifecycle/versioning policy first: one day
for deliveries, 90 for presentations. Before vendor use validate actual export
safe URL metadata; [vendor docs](https://docs.slidespeak.co/v1/reference/download)
show the global host but do not prove every regional/path/signature shape.

Recreate avoids old/new helper overlap during updates; plan downtime and stop
in-flight transfers. Verify old pods are gone and new operation enforcement,
full hashing and cleanup behavior, not merely listener health. Retain the
immutable `app=agent-pipe-uploader` selector and single ownership; remove any
legacy standalone resource in its separately reviewed migration.

The existing 1 GiB shared artifact PVC has no reservation or per-session quota.
Stage at most one deck per request, sequentially, within 100 MiB. Stop on known
insufficient capacity; otherwise disclose uncertainty, not a free-space guarantee.
ENOSPC fails/cleans a partial download; interrupted-process leftovers need
explicit handling. No blind eviction, auto-delete or new capacity tool.

Helper-only rendered tests run through `make test-retained-presentations` and
assert no client version or permission. See
[Uploader rollout](../docs/retained-presentation-uploader.md). Publication does
not update its GitOps pin: the manual helper pin and verified reconciliation
must precede the separate client release. No new automation is introduced.
