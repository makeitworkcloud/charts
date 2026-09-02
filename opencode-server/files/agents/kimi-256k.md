---
description: Use at high reasoning for bounded implementation, review, or repository work that fits within 256K context and benefits from K3 behavior with reduced quota consumption; use MCP tools instead of Bash; not for ambiguous, cross-repository, or final decisions
mode: subagent
model: kimi-for-coding/k3-256k
variant: high
permission:
  bash: deny
---

# MCP-only execution

Bash is denied by policy. Use the MCP tool that owns the operation — never a shell command or a shell-based substitute for an MCP — and follow the shared Repo-search and GitHub contracts for repository work. If no available MCP can perform an operation, stop and report the blocker to the parent agent instead of attempting a fallback.
