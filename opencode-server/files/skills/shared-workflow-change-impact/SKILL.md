---
name: shared-workflow-change-impact
description: Use when changing shared-workflows reusable Actions or assessing their caller, permission, runner, and image compatibility impact.
---

# Shared workflow changes

Treat reusable workflow inputs, permissions, trigger behavior, runner labels, and emitted checks as a public interface to every caller.

Before editing, identify callers and the matching `images/tfroot-runner` runtime contract. Do not add nested job containers to ARC runner workflows. Validate through the workflow repository PR and representative consumer evidence where available. Never dispatch workflows or alter consumers without explicit confirmation.
