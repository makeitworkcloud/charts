---
name: cloud-artifact-transfer
description: Use when moving a non-sensitive artifact between `/artifacts` and approved cloud storage through a signed URL, or removing a verified delivered staging file.
---

# Cloud artifact transfer

Cloud MCPs own account discovery, IAM, bucket controls, metadata and presigning.
The existing `agent-pipe` MCP owns bytes under `/artifacts`, has no cloud
credentials or home-PVC mount, and cannot administer or delete S3 objects.
Never bypass it with native exec, shell, fetch tools, credentials or arbitrary
URLs. Never transfer secrets, state, decrypted SOPS, kubeconfigs, private keys,
raw logs, sensitive documents or submission archives.

## Profiles and URL boundaries

- `agent-pipe`: upload/download/verify, existing private bucket `agent-pipe`,
  `/deliveries/`, one-day retention for ordinary non-sensitive artifacts.
- `agent-presentations`: upload/download/verify, SAME bucket, `/presentations/`,
  approved 90-day retention only for user-directed non-sensitive generated decks.
- `slidespeak-exports`: download/verify ONLY, exact hosts
  `slidespeak-files.s3.amazonaws.com` and
  `slidespeak-files.s3.us-east-2.amazonaws.com`, path prefix `/`.
- All profiles cap transfers at 104857600 bytes (100 MiB). Verify deployed
  helper/image readiness before using new profiles or cleanup: explicit
  `upload`, `download`, `verify` operations must fail closed when missing or
  disallowed, and verification must return full-response bytes and SHA-256.
  An unpublished staging pin or healthy listener is not readiness evidence.
- Before vendor transfer, check actual tool-produced URL safe metadata: HTTPS,
  exact allowed host, nonempty object path, and unique nonempty query fields
  `X-Amz-Algorithm`, `X-Amz-Credential`, `X-Amz-Date`, `X-Amz-Expires`,
  `X-Amz-SignedHeaders`, `X-Amz-Signature`. Never print query values. Preserve
  the original signature byte-for-byte; no redirects or allowlist expansion.

Never persist signed URLs in files, logs, knowledge, commits or durable delivery
records. Never return PUT URLs. Two explicit transient user-output exceptions:
a fully tested S3 GET link under `s3-presigned-file-delivery`, or a SlideSpeak
GET download link returned by `slidespeak_downloadPresentation` for the recorded
`request_id` when retention is unavailable or declined. Label the latter
TEMPORARY, NOT ARCHIVED; provider expiry is unspecified unless the tool supplies
it. Do not claim it was helper-tested when it was not. No arbitrary vendor URLs.

## Stage, transfer and verify

1. Select the policy/profile/key for the actual artifact under the S3 skill.
   Presentation-specific preflight applies only to retained decks, not ordinary
   `deliveries/` or generic existing-object GET requests.
2. Use a new normalized relative staging path under `/artifacts`, never
   overwrite or follow symlinks. Retained decks use
   `presentations/<session-id>/<artifact-id>/presentation.<ext>` as both path
   and key. Use a trusted actual session ID, or allocate and label a unique
   delivery token if unavailable; never guess. Use a collision-resistant
   artifact ID. Derive `<ext>` from the verified tool request's `response_format`:
   `powerpoint` means `pptx`, `pdf` means `pdf`. Confirm an omitted format's
   documented default; never infer format from an untrusted URL/file extension
   or expand/parse bytes to guess it. Preserve ordinary artifact filenames and
   extensions instead of renaming them as presentations.
3. Obtain exact download approval for profile, source reference and destination
   before `agent-pipe_download_artifact`. Compare its measured bytes/SHA-256
   with `agent-pipe_inspect_artifact`. Decks must have positive size <=100 MiB.
4. Complete the applicable S3 preflight and obtain exact upload approval for
   path, profile, bucket/key and retention. Call `agent-pipe_upload_artifact`
   with the unchanged signed PUT. Retention approval never waives prompts;
   never choose always-allow.
5. Compare upload byte count and a fresh local inspection to the original
   identity. Check HeadObject metadata and fully read/hash the signed S3 GET
   through `agent-pipe_verify_download`. Require bytes/SHA-256 equality, not
   ETag, HEAD, a one-byte probe or upload success. Return the durable reference
   and the same tested S3 GET only after successful verification.

## Capacity and retries

The existing 1 GiB shared artifact PVC has no per-session reservation or quota.
The 100 MiB per-file bound is not available-space assurance. Stage at most one
deck per request and transfer sequentially; account for other writers and
staging overhead. Stop on known insufficient capacity. If capacity is uncertain
and no approved discovery tool/evidence is available, report lack of assurance,
not guaranteed space; uncertainty alone does not require an unconditional stop.
The helper's ENOSPC/write failure fails the download and cleans its partial
temporary file; do not claim success, retry blindly or evict other files.
An interrupted process may leave leftovers requiring explicit operator handling.
No new capacity tool, reservation, native exec or automatic deletion is added.

For expiry/transient failures allow one fresh signed URL and one sequential
retry within the approved scope. Inspect an ambiguous destination/object first;
never overwrite, regenerate the deck or create unexpected versions. Permission,
profile, integrity and known capacity failures need resolution, not blind retry.

## Explicit cleanup

Only AFTER stored bytes/hash are verified AND the durable reference has been
returned, offer cleanup. Require the exact removal prompt naming the relative
path and expected SHA-256, then call
`agent-pipe_remove_artifact(artifact, expected_sha256)`. It removes only that
regular file, never directories or symlinks; it does not delete S3 data. No
automatic cleanup, S3 DeleteObject or native exec grant is introduced. Refusal
or failure leaves the file; never claim removal without tool success.
