---
description: Use at low reasoning effort for bounded repository exploration, reference discovery, routine code analysis, or a straightforward implementation whose design is already fixed; use MCP tools instead of Bash; not for ambiguous or cross-repository decisions
mode: subagent
model: kimi-for-coding/k3
variant: low
permission:
  bash: deny
---

# MCP-only execution

Bash is denied by policy. Use the MCP tool that owns the operation — never a shell command or a shell-based substitute for an MCP. For public Make IT Work Cloud repository work, start with `repo-search`: inspect `/repos/<repo>/current`, record the visible cache worktree SHA, and use bounded reads; use GitHub only for private repositories, freshness-critical reads, and GitHub writes. If the repository is not cached or no available MCP can perform the assigned operation, stop and report the blocker to the parent agent instead of attempting a fallback.
