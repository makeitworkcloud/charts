# Retained presentations: combined staging

This branch is a combined review snapshot, not a release unit. Use the separate
uploader and client branches based on the same main snapshot. No PR, publication,
local tests or live mutations are implied by these commits.

1. Confirm separately approved storage apply and private prefix/IAM/lifecycle/
   versioning evidence: deliveries one day, presentations 90 days.
2. Verify helper main-image publication, replace the UNPUBLISHED
   `63ccfde32e70decf81255e816cd2ada57b4f7e10` staging pin with that immutable
   SHA/digest BEFORE uploader chart merge. Never `latest`.
3. Publish uploader 0.3.0, manually pin it in GitOps, and separately authorize
   reconciliation. Verify no old pods, operation enforcement, full hashing and
   exact-file removal. Safe actual vendor URL metadata remains an activation gate.
4. Only with deployed-helper proof may the client 0.4.7 draft merge. Its existing
   server-only automatic GitOps pin workflow remains unchanged. No source-only
   uploader assertion substitutes for runtime evidence.

Helper tests render only the helper. Client tests render only the server and
check permission plus policy wording; neither suite depends on the other chart's
new version. Existing historical baseline/model/#118 guards remain intact.
The three skill replacements have fixed old/new blob identities; this is not a
baseline bypass. Static checks do not prove real delivery behavior.

Ordinary artifacts keep their filename/extension and deliveries policy. Existing
S3 GETs do not acquire retained-deck prerequisites or reset retention. Generated
decks preserve requested PPTX or PDF format, selected from the verified tool
request rather than an untrusted extension. Both stored verification and staged
inspection compare full bytes/SHA-256. S3 links are tested, 900-second GETs.
If retention is unavailable/declined, a tool-returned SlideSpeak GET may be
returned transiently as TEMPORARY, NOT ARCHIVED, with unspecified provider expiry
unless reported. Fresh vendor links reuse request_id, never generation.
No PUT URL output or durable signed-URL persistence is permitted.

The shared 1 GiB PVC is not reserved/quota-isolated. Stage one deck per request,
sequentially, capped at 100 MiB; stop on known insufficiency and disclose unknown
capacity without guaranteeing it. ENOSPC fails/cleans the partial file. No blind
eviction or new tool. Cleanup still requires exact approval after verified
storage and return of the durable reference. Sensitive/submission policy is
unchanged. No dependencies, services, native exec or S3 delete grants are added.
