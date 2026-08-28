---
name: opentofu-root-change
description: Use when changing a makeitworkcloud tfroot-* repository or terraform-libvirt-domain. Covers ownership, CI planning, and state safety.
---

# OpenTofu root changes

1. Read the root `AGENTS.md`, README, caller workflow, and `images/tfroot-runner` ownership notes.
2. Treat PR CI plans as the only validation evidence. Never run init, plan, apply, import, taint, or state commands from this server.
3. Keep SOPS files encrypted. Do not retrieve, print, or commit plaintext, state, credentials, or sensitive plan output.
4. Create a scoped branch and PR for an authorized code change; main is an apply path and requires no direct push.
5. If CI fails, inspect workflow/check evidence and make only the narrow fix. A live operation always needs explicit confirmation.
