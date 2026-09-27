---
name: career-external-documents
description: Use when generating presentation decks with SlideSpeak through the configured MCP service, including retained delivery and fresh links for user-directed non-sensitive decks.
---

# Career external documents

Use SlideSpeak only for presentation decks the owner asks for. This retained
workflow applies to ALL user-directed non-sensitive SlideSpeak decks, not only
career presentations. Text resumes and documents retain their existing document
pipeline; this skill grants no workstation access or new external service.

## Generate once, then offer retention

1. Confirm the requested deck and external-generation content scope. Use the
   existing SlideSpeak MCP proxy only. Generate once, poll within the tool's
   task contract and retain the returned `request_id` (not just `task_id`).
2. Offer the approved private 90-day retained delivery with fresh 900-second
   S3 links on request. Retention approval does not waive exact download,
   upload or removal permission prompts. Do not archive without those approvals.
3. Load `cloud-artifact-transfer` and `s3-presigned-file-delivery`. Before
   storing, complete their account/region/privacy/lifecycle/versioning and
   deployed-helper/profile prerequisites. Use the same existing bucket and
   artifact PVC, never a new service or public storage.
4. Call `slidespeak_downloadPresentation(request_id)` to obtain a temporary
   export capability. Verify safe URL metadata (HTTPS, exact allowed host,
   nonempty object path and required SigV4 parameter names) before enabling
   transfer. Never print the signed vendor URL or query values. Official
   [download documentation](https://docs.slidespeak.co/v1/reference/download)
   describes `slidespeak-files.s3.amazonaws.com` and refreshing by `request_id`;
   documentation alone does not prove every live export's regional host,
   path or signature shape. The configured second exact host is
   `slidespeak-files.s3.us-east-2.amazonaws.com`; validate an actual response
   safely before use. A mismatch is a blocker, not an allowlist expansion.
5. After the exact download prompt, stage with profile `slidespeak-exports` at
   `presentations/<session-id>/<artifact-id>/presentation.pptx` relative to
   `/artifacts`. Use a trusted actual session ID or explicitly labeled unique
   delivery token, never guess. Require positive size at most 100 MiB, inspect
   the staged regular file and compare full SHA-256 and measured bytes.
6. After the exact upload prompt, use `agent-presentations` with the same key
   in the private `agent-pipe` bucket. Follow the S3 skill's HeadObject metadata
   and full GET hash/byte verification, then return the durable reference and
   SAME tested short-lived S3 link. Only afterward offer separately approved
   exact-file cleanup with `expected_sha256`.
7. Record only non-sensitive bucket/key/region, `request_id`, bytes, SHA-256,
   creation time and requested retention metadata in the authorized session
   record. Never persist signed URLs or submitted-application artifacts.
   Fresh-link requests reuse the verified S3 reference without generation.

## Incomplete delivery

If AWS, image, profile, capacity or source-shape prerequisites are missing,
report archive INCOMPLETE and retain `request_id`. Offer temporary vendor
 delivery through the existing SlideSpeak export/reference workflow, clearly
not retained; return a non-signed presentation reference if available, never
print a vendor signed URL or claim that a request ID proves a persisted S3
object. If no safe deliverable reference is available, state that limitation.
For an expired export, request a fresh URL once with the SAME `request_id` and
retry once sequentially within the approved scope; never generate again to fix
an expired URL. Do not auto-delete local files to resolve capacity.

## Availability and data boundary

SlideSpeak authentication stays in the cluster-owned direct proxy. On service,
authentication or plan failure, stop and report it: no retry loop, OAuth,
credential handling or replacement service. Do not transfer secrets or
sensitive documents. Send only the deck content the owner explicitly requested;
never send `career-data.yaml`, tracker contents or whole documents wholesale
unless the owner named that document for external generation. Retention approval
is for non-sensitive generated decks, not submissions or sensitive source
records; existing sensitive-document and submission policies are unchanged.
