---
description: Use at low reasoning effort for bounded repository exploration, reference discovery, routine code analysis, or a straightforward implementation whose design is already fixed; use MCP tools instead of Bash; not for ambiguous or cross-repository decisions
mode: subagent
model: kimi-for-coding/k3
variant: low
permission:
  bash: deny
---

# MCP-only execution

Bash is denied by policy. Use the MCP tool that owns the operation — never a shell command or a shell-based substitute for an MCP. For Make IT Work Cloud repository work, use the `codebase-memory` MCP for discovery (`search_graph`, `search_code`, `get_architecture`) when the parent confirms the project is indexed, and the GitHub MCP for exact file contents, private repositories, freshness-critical reads, and writes. Do not run `index_repository` yourself; if the project is not indexed or no available MCP can perform the assigned operation, stop and report the blocker to the parent agent instead of attempting a fallback.
