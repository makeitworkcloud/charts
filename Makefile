.PHONY: changed-charts list-charts list-charts-json package-chart test test-opencode-server-agents

SHELL := /bin/bash
CHARTS := $(shell find . -maxdepth 2 -name Chart.yaml -printf '%h\n' | cut -d'/' -f2 | sort -u)

changed-charts:
	@changed=$$(git diff --name-only HEAD~1 HEAD 2>/dev/null | cut -d'/' -f1 | sort -u); \
	for chart in $(CHARTS); do echo "$$changed" | grep -qx "$$chart" && echo "$$chart"; done | jq -R -s -c 'split("\n") | map(select(length > 0))'

list-charts:
	@for chart in $(CHARTS); do echo "$$chart"; done

list-charts-json:
	@echo '$(CHARTS)' | tr ' ' '\n' | jq -R -s -c 'split("\n") | map(select(length > 0))'

package-chart:
	@test -n "$(CHART)"
	@helm package "$(CHART)" --destination "$(DESTINATION)"

test:
	@for chart in $(CHARTS); do helm lint --strict "$$chart" && helm template test "$$chart" > /dev/null; done
	@$(MAKE) test-opencode-server-agents

test-opencode-server-agents:
	@set -euo pipefail; \
	expected="$$(printf '%s\n' '---' "description: Use for bounded generic coding, debugging, or repository tasks when the assigning primary agent's execution budget is nearing completion or it otherwise needs execution capacity; the primary retains task interpretation, safety, delivery decisions, and final synthesis" 'mode: subagent' 'model: openai/gpt-5.6-terra' 'variant: default' '---')"; \
	test "$$(cat opencode-server/files/agents/terra.md)" = "$$expected"; \
	grep -Fqx 'version: 0.2.1' opencode-server/Chart.yaml; \
	grep -Fqx '  "default_agent": "default",' opencode-server/files/opencode.json; \
	rendered="$$(helm template test opencode-server)"; \
	printf '%s\n' 'default makeitwork xnoto career teacher grillmaster homerepair homesteader lawnmowerman' | tr ' ' '\n' | while IFS= read -r agent; do \
		source="opencode-server/files/agents/$$agent.md"; \
		test -s "$$source"; \
		grep -Fqx 'mode: primary' "$$source"; \
		grep -Eiq 'index_repository.*full|full.*index_repository' "$$source"; \
		grep -Fq 'Module' "$$source"; \
		grep -Fq 'search_graph' "$$source"; \
		grep -Fq 'get_code_snippet' "$$source"; \
		grep -Eiq 'range (begins|starts) at line 1' "$$source"; \
		grep -Eiq 'complete and unclipped' "$$source"; \
		grep -Eiq 'fallback|fall back' "$$source"; \
		grep -Fq 'GitHub' "$$source"; \
		echo "$$rendered" | grep -Fqx "  $$agent.md: |-"; \
		echo "$$rendered" | grep -Fqx "              - key: $$agent.md"; \
		echo "$$rendered" | grep -Fqx "                path: agents/$$agent.md"; \
	done; \
	printf '%s\n' 'kimi kimi-256k' | tr ' ' '\n' | while IFS= read -r agent; do \
		source="opencode-server/files/agents/$$agent.md"; \
		test -s "$$source"; \
		grep -Fqx 'mode: subagent' "$$source"; \
		grep -Eiq 'index_repository.*full|full.*index_repository' "$$source"; \
		grep -Fq 'Module' "$$source"; \
		grep -Fq 'search_graph' "$$source"; \
		grep -Fq 'get_code_snippet' "$$source"; \
		grep -Eiq 'range (begins|starts) at line 1' "$$source"; \
		grep -Eiq 'complete and unclipped' "$$source"; \
		grep -Eiq 'fallback|fall back' "$$source"; \
		grep -Fq 'GitHub' "$$source"; \
		echo "$$rendered" | grep -Fqx "  $$agent.md: |-"; \
		echo "$$rendered" | grep -Fqx "              - key: $$agent.md"; \
		echo "$$rendered" | grep -Fqx "                path: agents/$$agent.md"; \
	done; \
	echo "$$rendered" | grep -Fqx '  terra.md: |-'; \
	echo "$$rendered" | grep -Fqx "    description: Use for bounded generic coding, debugging, or repository tasks when the assigning primary agent's execution budget is nearing completion or it otherwise needs execution capacity; the primary retains task interpretation, safety, delivery decisions, and final synthesis"; \
	echo "$$rendered" | grep -Fqx '    mode: subagent'; \
	echo "$$rendered" | grep -Fqx '    model: openai/gpt-5.6-terra'; \
	echo "$$rendered" | grep -Fqx '    variant: default'; \
	echo "$$rendered" | grep -Fqx '              - key: terra.md'; \
	echo "$$rendered" | grep -Fqx '                path: agents/terra.md'; \
	archive_dir="$$(mktemp -d)"; \
	trap 'rm -rf "$$archive_dir"' EXIT; \
	helm package opencode-server --destination "$$archive_dir" > /dev/null; \
	archive="$$(find "$$archive_dir" -maxdepth 1 -type f -name 'opencode-server-0.2.1.tgz' -print -quit)"; \
	test -n "$$archive"; \
	printf '%s\n' 'default makeitwork xnoto career teacher grillmaster homerepair homesteader lawnmowerman kimi kimi-256k' | tr ' ' '\n' | while IFS= read -r agent; do \
		source="opencode-server/files/agents/$$agent.md"; \
		entry="opencode-server/files/agents/$$agent.md"; \
		tar -tzf "$$archive" | grep -Fqx "$$entry"; \
		tar -xOzf "$$archive" "$$entry" | cmp -s - "$$source"; \
	done
