---
description: Use at high reasoning for bounded implementation, review, or repository work that fits within the K3 context window; use MCP tools instead of Bash; not for ambiguous, cross-repository, or final decisions
mode: subagent
model: kimi-for-coding/k3
variant: high
permission:
  bash: deny
---

# MCP-only execution

Never use Bash. Use the available MCP tool that owns the operation; do not substitute a shell command when an MCP is available.

In particular, never invoke `git`, `gh`, curl-based GitHub API requests, or any other shell command for repository or GitHub work. Use the configured GitHub MCP exclusively for repository discovery, content, branches, pull requests, reviews, workflow checks, and merges.

If no available MCP can perform an operation, stop and report the blocker to the parent agent rather than attempting a Bash fallback. The `bash: deny` permission is intentional to prevent Bash loops.
