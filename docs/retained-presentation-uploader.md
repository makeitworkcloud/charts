# Uploader release gate

Uploader-only draft, version 0.3.0. OpenCode sources/versions are not prerequisites
for its rendered tests. Namespace, existing Service identity and 1 GiB artifact
PVC ownership stay unchanged; no new dependencies, services or automation.

1. Confirm the separately approved storage apply and private account/region,
   prefix IAM, encryption, ownership, lifecycle and versioning evidence.
   Preserve deliveries one day; presentations require 90 days.
2. Verify successful helper main-image publication and registry identity.
   Replace staging source SHA `63ccfde32e70decf81255e816cd2ada57b4f7e10`
   with the published immutable SHA/digest BEFORE chart merge. Squash merge
   changes the SHA. The current placeholder is BLOCKED, not a published image.
3. Obtain future PR hygiene, Helm/render and uploader package evidence. No
   tests/publication are claimed on this draft. Merge/publish need approval.
4. Manually pin published uploader 0.3.0 in GitOps; existing server auto-pin
   automation does not update it. Separately authorize reconciliation, drain
   in-flight transfers and verify Recreate completion with no old helper pods.
5. Verify explicit operation enforcement (vendor upload denied, missing
   operations fail closed), full bytes/SHA-256 and exact regular-file cleanup.
   Validate actual tool-returned vendor HTTPS host/path/SigV4 safe metadata
   without printing signatures. Health endpoints alone do not prove readiness.
6. Return deployed-helper evidence to the client release reviewer. Only then
   may the separate client draft merge and trigger its existing auto-pin path.

Do not merge the combined staging branch as a release. No live operation is
authorized by this document. No new capacity tool or eviction: unknown shared
space is disclosed; known insufficiency stops transfer, ENOSPC fails/cleans a
partial download, and interrupted leftovers require explicit handling.
