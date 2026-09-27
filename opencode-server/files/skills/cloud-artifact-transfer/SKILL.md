---
name: cloud-artifact-transfer
description: Use when moving a non-sensitive artifact between `/artifacts` and approved cloud storage through a signed URL, or removing a verified delivered staging file.
---

# Cloud artifact transfer

Use the existing `agent-pipe` MCP for data-plane transfers under `/artifacts`.
Cloud MCPs own discovery, IAM, bucket controls, object metadata and presigning.
The helper has no cloud credentials, cannot administer or delete S3 objects,
and never mounts the OpenCode home PVC. No native exec, shell, fetch tool,
credential handling, arbitrary URL, or other service may bypass this boundary.

## Profiles and readiness

- `agent-pipe`: upload/download/verify for the private `agent-pipe` bucket's
  `deliveries/` prefix; existing one-day lifecycle policy remains unchanged.
- `agent-presentations`: upload/download/verify for the SAME bucket's
  `presentations/` prefix, with owner-approved 90-day retention.
- `slidespeak-exports`: download/verify ONLY from exact hosts
  `slidespeak-files.s3.amazonaws.com` and
  `slidespeak-files.s3.us-east-2.amazonaws.com`, path prefix `/`.
- Each profile is capped at 104857600 bytes (100 MiB). Missing operations must
  fail closed. Before use verify the deployed helper supports explicit
  `upload`, `download`, `verify`, full-response SHA-256 and `remove_artifact`;
  configuration or a healthy listener alone is not proof. Never use the
  unpublished staging image placeholder or an old helper for this workflow.
- Before enabling vendor transfers verify the actual source URL's safe metadata
  against the documented HTTPS host/path shape and required query parameter
  names: `X-Amz-Algorithm`, `X-Amz-Credential`, `X-Amz-Date`, `X-Amz-Expires`,
  `X-Amz-SignedHeaders`, `X-Amz-Signature`. Do not print their values. The
  download URL must come from the configured SlideSpeak tool for the recorded
  `request_id`, never an arbitrary user/page URL. A redirect, host mismatch or
  unsupported signing shape is a blocker, not permission to widen the profile.

Never transfer secrets, credentials, OpenTofu state, decrypted SOPS values,
kubeconfigs, private keys, raw logs, sensitive documents or submission archives.
Signed URLs are bearer capabilities: never persist them in files, logs, durable
records, knowledge or commits. Never print vendor URLs or PUT URLs. The sole
user-output exception is the same successfully tested short-lived S3 GET link
under `s3-presigned-file-delivery`; supply it transiently, not in a saved record.

## Transfer and verification

1. Confirm the exact user-directed non-sensitive artifact, approved profile,
   source reference, destination path and object key. Run the S3 skill's account,
   region, privacy, lifecycle and versioning preflight before storing anything.
2. Stage at a new normalized relative path under `/artifacts`, never overwrite
   a file or follow a symlink. For retained decks use
   `presentations/<session-id>/<artifact-id>/presentation.pptx` both as the
   relative staging path and S3 key. Use the actual trusted session identifier;
   if unavailable allocate a unique delivery token and label it as such, never
   guess a session ID. Use a separate collision-resistant artifact ID.
3. Obtain the exact download permission prompt before
   `agent-pipe_download_artifact(profile_name, signed_get_url, destination)`.
   Preserve the original URL byte-for-byte, including its signature. Require
   measured bytes and SHA-256, then call `agent-pipe_inspect_artifact` and
   compare both fields. For decks require positive size at most 100 MiB.
4. Obtain the exact upload permission prompt naming relative artifact path,
   profile, bucket/key and requested retention. Call `agent-pipe_upload_artifact`
   with the unchanged PUT URL. Never treat retention approval as transfer
   approval or choose always-allow.
5. Inspect the staged file again and compare bytes/hash with its download
   result. Check S3 `HeadObject` metadata, then use `agent-pipe_verify_download`
   on a freshly signed S3 GET. It must read the FULL response and return matching
   `bytes` and `sha256`. ETag, HEAD, a one-byte probe, upload success or a
   syntactically valid URL is not integrity/delivery verification.
6. Return the verified durable reference and the tested S3 GET link under the
   S3 skill. Keep only non-sensitive bucket, key, region, `request_id`, hash,
   bytes, creation time and requested retention metadata in the session record.

## Capacity, retries and explicit cleanup

Transfer sequentially. A 100 MiB file cap is not free-space assurance or a PVC
quota. Account for existing files, temporary staging, other writers and full
GET verification costs; if capacity is unknown or insufficient, report it and
stop rather than deleting other artifacts. Never auto-delete or evict files.
On an expiry/transient transfer failure, refresh the relevant signed URL once
and retry once, sequentially, only within the exact approved transfer scope.
Check for a completed destination/object first after an ambiguous result; do
not overwrite, regenerate a deck, loop, or create unexpected S3 versions.
Authorization, profile, integrity or capacity failures require resolution, not
blind retry. Keep the request ID when archiving is incomplete.

Only AFTER the stored object is fully verified AND its durable reference has
been returned, offer cleanup. Obtain the exact removal prompt for the relative
file path and expected SHA-256, then call
`agent-pipe_remove_artifact(artifact, expected_sha256)`. This removes only that
regular file, never directories or symlinks; it does not delete S3 data. Refusal
or failure leaves the file for explicit later handling. No native exec or S3
DeleteObject permission is added. Never claim cleanup without a successful
result. Existing approvals and sensitive-document policy remain unchanged.
