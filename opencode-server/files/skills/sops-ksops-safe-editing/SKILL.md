---
name: sops-ksops-safe-editing
description: Use when editing SOPS-encrypted files, KSOPS generators, Kubernetes Secrets, or OpenTofu secret inputs.
---

# SOPS and KSOPS safety

Keep sensitive material encrypted and never print, summarize, commit, or retrieve decrypted values.

- Encrypt only the fields defined by the repository `.sops.yaml` policy.
- Keep one Kubernetes Secret per file and preserve KSOPS generator references.
- Do not encrypt non-secret manifests or metadata unless repository policy explicitly requires it.
- Never use this server to decrypt, edit plaintext secrets, or access age/KMS credentials.

When a change needs secret material, describe the canonical encrypted source and the CI/GitOps validation path without exposing values.
