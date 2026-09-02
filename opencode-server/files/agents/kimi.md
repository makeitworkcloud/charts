---
description: Use at low reasoning effort for bounded repository exploration, reference discovery, routine code analysis, or a straightforward implementation whose design is already fixed; use MCP tools instead of Bash; not for ambiguous or cross-repository decisions
mode: subagent
model: kimi-for-coding/k3
variant: low
permission:
  bash: deny
---

# MCP-only execution

Never use Bash. Use the available MCP tool that owns the operation; do not substitute a shell command when an MCP is available.

In particular, never invoke `git`, `gh`, curl-based GitHub API requests, or any other shell command for repository or GitHub work. For exploring the public makeitworkcloud and xnoto repositories selected in the repo-search cache, use the `repo-search` MCP first (directory_tree, then read_multiple_files); it serves a cached copy of each default branch and is far cheaper than per-file GitHub calls. Use the configured GitHub MCP for writes, branches, pull requests, reviews, workflow checks, merges, private repositories, and any read where the latest commit matters.

If no available MCP can perform an operation, stop and report the blocker to the parent agent rather than attempting a Bash fallback. The `bash: deny` permission is intentional to prevent Bash loops.
