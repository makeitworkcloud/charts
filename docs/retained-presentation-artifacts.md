# Retained presentation artifacts

This is a staged contract for the existing SlideSpeak, AWS and agent-pipe
services, not a claim of deployed capability. It adds no dependencies, services,
credentials, workflow automation, native exec grants or S3 delete permission.
Only user-directed non-sensitive generated decks qualify; sensitive documents
and submission archives remain prohibited.

## Merge blockers

- `agent-pipe-uploader/values.yaml` contains UNPUBLISHED image source SHA
  `63ccfde32e70decf81255e816cd2ada57b4f7e10` as a staging-only placeholder.
  Before any chart merge, replace it with the verified main-published immutable
  image SHA/digest and record publication/registry evidence in the primary PR.
  Source branch identity is not registry identity; squash merge changes the SHA.
  Never use `latest` or infer that a 40-hex string has been published.
- Confirm applied private bucket/IAM/lifecycle/versioning prerequisites, not just
  an OpenTofu plan or merged source. `presentations/` must expire at 90 days
  without broader earlier expiry; preserve the one-day `deliveries/` rule.
- Validate actual SlideSpeak export safe URL metadata before enabling vendor
  transfers. Official [download docs](https://docs.slidespeak.co/v1/reference/download)
  show the global S3 hostname and permanent `request_id`; the regional hostname,
  object path and SigV4 fields must also match the actual export. Keep URL query
  values out of evidence. No arbitrary URL, wildcard host, redirect or signature
  rewriting fallback is permitted.

## Ordered rollout

1. Confirm the separately approved OpenTofu apply completed. Verify account,
   region, bucket owner, effective private access controls, encryption,
   bucket-owner-enforced ownership, prefix-scoped role access, lifecycle and
   versioning. No apply is authorized by this branch.
2. Merge/publish the helper image only under its separate approval. Verify its
   successful main publication and immutable registry identity. It must enforce
   explicit `upload`/`download`/`verify` operations (missing operations fail
   closed), full GET bytes/SHA-256, and exact-file hash-checked removal.
3. Replace the staging image pin BEFORE chart merge and obtain primary PR
   hygiene, Helm/render, baseline and packaging evidence. Release uploader 0.3.0
   first through an uploader-only reviewed release. Do not merge this combined
   staging branch as a single release if the consumer could auto-pin early.
4. Manually review and pin the published uploader 0.3.0 source in GitOps. The
   existing chart workflow does NOT update this source. Under separate rollout
   authorization, reconcile and verify Recreate completion, no old helper pods,
   published image identity, all three profiles and download-only vendor
   enforcement. Listener health alone is insufficient. Plan a brief outage and
   no in-flight transfers; no workflow broadening is proposed.
5. Only after helper reconciliation/verification, release OpenCode 0.4.7 (or a
   fresh version if already occupied). Its existing post-publish workflow opens
   the server-only GitOps pin PR and enables auto-merge after destination checks.
   Publication of both charts does not order reconciliation. If releasing from
   this staging branch, split producer and consumer changes into ordered PRs
   before merge; do not rely on automation to hold the server pin.
6. After the separately authorized server rollout, verify configuration in a
   fresh session, including exact download/upload/remove prompts. Configuration
   loads at startup, not hot reload. Verify representative non-sensitive
   delivery, reissue and cleanup separately from static CI. No live operation is
   authorized by documenting these gates.

## Delivery contract

Use `presentations/<session-id>/<artifact-id>/presentation.pptx` as both the S3
key and relative `/artifacts` staging path. The session identifier must be
trusted metadata; otherwise allocate and label a unique delivery token, never
pretend it is a real session ID. Artifact IDs must be collision-resistant.
Transfers are sequential, capped at 100 MiB, and require exact user prompts.
Retaining for 90 days does not grant blanket transfer or cleanup approval.

Compare download and local inspection bytes/SHA-256, upload byte count, a fresh
local inspection, exact-key HeadObject metadata, and a full S3 GET through
`verify_download`. Never substitute ETag or a HEAD/probe for full content
verification. Check for unexpected versions and existing destinations before
retrying an ambiguous result. Allow one fresh signed URL and one retry per
expiry/transient failure, not an unbounded loop or presentation regeneration.

Return a durable bucket/key/region reference and keep non-sensitive
`request_id`, bytes, SHA-256, creation time and requested retention metadata in
the authorized session record. Signed URLs never enter durable files/records.
The ONLY signed URL in user output is the same tested 900-second S3 GET link,
supplied transiently with expiry caveats. Vendor and PUT URLs are never printed.
A later fresh-link request retrieves the same retained object, verifies against
the recorded identity, and never regenerates the deck. Lifecycle expiry is
asynchronous and distinct from link expiry.

No auto-delete, recursive cleanup or S3 deletion is introduced. The shared PVC
has finite capacity; a per-file cap is not a volume quota. Account for concurrent
writers and staging overhead; if capacity cannot be established, stop/report.
Only after verified storage and returning the durable reference may the user
approve removal of the exact local regular file with its expected SHA-256.
Directories and symlinks are refused. No cleanup claim without tool success.

If AWS, profile, source shape, capacity or image prerequisites are missing,
report archive INCOMPLETE, preserve `request_id`, and offer temporary vendor
export/reference delivery, explicitly not persisted. Do not expose a vendor
signed URL; if no safe reference can be returned, report that limitation. No
credential workaround or new service is allowed.

## Validation evidence

The existing PR workflow runs hygiene, `make test`, changed-chart detection and
packaging for both changed charts. `make test` includes focused rendered profile,
prefix, SigV4, limit, approval, immutable-pin-shape and no-home-mount checks.
Image publication is a manual evidence gate, not established by a pin-shape test.
The historical memory-pilot baseline stays at 0.4.0 (`32a6b91`); all #118 agent,
model and policy guards remain intact. Only an exact cleanup permission line
and three old/new Git-blob-pinned skill replacements extend its allowlist.
No dynamic copy of unverified current skills or ignored ConfigMap keys is used.

Feature-branch pushes do not trigger this repository's workflow. With no PR,
no tests or packaging/publication evidence are claimed. The future primary PR
must supply those checks; live storage/source/image acceptance remains separate.
