---
description: Use at low reasoning effort for bounded repository exploration, reference discovery, routine code analysis, or a straightforward implementation whose design is already fixed; use MCP tools instead of Bash; not for ambiguous or cross-repository decisions
mode: subagent
model: kimi-for-coding/k3
variant: low
permission:
  bash: deny
---

# MCP-only execution

Bash is denied by policy. Use the MCP tool that owns the operation — never a shell command or a shell-based substitute for an MCP — and follow the shared Repo-search and GitHub contracts for repository work. If no available MCP can perform an operation, stop and report the blocker to the parent agent instead of attempting a fallback.
