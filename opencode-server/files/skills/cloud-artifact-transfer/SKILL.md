---
name: cloud-artifact-transfer
description: Use when moving a non-sensitive artifact between `/artifacts` and approved cloud storage through a signed URL.
---

# Cloud artifact transfer

Use the `agent-pipe` MCP service only to move bytes through a configured,
capability-scoped transfer profile. It is not a cloud administration service.

## Boundaries

- Cloud MCPs own resource discovery, bucket configuration, IAM, object metadata,
  and signed URL generation. Do not use `agent-pipe` to replace them.
- `agent-pipe` owns data-plane transfer for files under `/artifacts`; it has no
  cloud credentials and cannot list, delete, or administer buckets.
- The currently configured profile is `agent-pipe`, for the private S3 bucket's
  `deliveries/` prefix. Do not invent a profile or use an arbitrary URL.
- Never transfer OpenTofu state, credentials, decrypted SOPS values, kubeconfigs,
  private keys, raw logs, or other sensitive content.
- Signed URLs are bearer capabilities. Do not print, quote, persist, or include
  them in user-facing output.

## Inspect

Use `agent-pipe_inspect_artifact` before a transfer when file size or identity
needs verification. It returns non-sensitive metadata for an existing file under
`/artifacts`.

## Upload and verify

1. Confirm the artifact is user-directed and non-sensitive.
2. Use the appropriate cloud MCP to verify the target account, region, bucket,
   and object-key policy, then mint a short-lived PUT URL for the approved profile.
3. Ask for explicit confirmation showing the artifact path and object key, but
   never the signed URL.
4. After approval, call `agent-pipe_upload_artifact` with the profile, relative
   artifact path, and unchanged signed URL. Its permission prompt must be approved
   for that exact transfer only.
5. Verify the uploaded object through the cloud MCP. Then mint a short-lived GET
   URL and call `agent-pipe_verify_download` with the same profile before sharing
   it with the user.

## Download

1. Confirm the destination is a new, non-sensitive relative path under
   `/artifacts` and will not overwrite another artifact.
2. Use the cloud MCP to mint a short-lived GET URL for an approved profile.
3. Ask for explicit confirmation before calling `agent-pipe_download_artifact`.
4. Inspect the resulting artifact before using or sharing it.

The `agent-pipe_upload_artifact` and `agent-pipe_download_artifact` tools are
approval-gated. Do not use an always-allow decision for transfers.
