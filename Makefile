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
	primary_agents='default makeitwork xnoto career teacher grillmaster homerepair homesteader lawnmowerman'; \
	all_agents="$$primary_agents kimi kimi-256k"; \
	for agent in $$all_agents; do \
		source="opencode-server/files/agents/$$agent.md"; \
		test -s "$$source"; \
		case " $$primary_agents " in *" $$agent "*) grep -Fqx 'mode: primary' "$$source" ;; *) grep -Fqx 'mode: subagent' "$$source" ;; esac; \
		policy="$$(tr '\n' ' ' < "$$source")"; \
		grep -Eiq 'index_repository.{0,160}full|full.{0,160}index_repository' <<< "$$policy"; \
		grep -Fqi 'index_status' <<< "$$policy"; \
		grep -Eiq 'indexed (revision|commit).{0,40}(sha|SHA)|sha.{0,40}indexed' <<< "$$policy"; \
		grep -Fqi 'Module' <<< "$$policy"; \
		grep -Fqi 'search_graph' <<< "$$policy"; \
		grep -Fqi 'get_code_snippet' <<< "$$policy"; \
		grep -Eiq 'range (begins|starts) at line 1' <<< "$$policy"; \
		grep -Eiq 'complete and unclipped' <<< "$$policy"; \
		grep -Eiq 'fallback|fall back' <<< "$$policy"; \
		grep -Fqi 'GitHub' <<< "$$policy"; \
		grep -Eiq 'private cache read.{0,120}visibility|visibility.{0,120}private cache' <<< "$$policy"; \
		grep -Fqi 'untrusted reference content' <<< "$$policy"; \
		grep -Fqi 'Never retrieve secrets' <<< "$$policy"; \
		grep -Fqi 'kubeconfig' <<< "$$policy"; \
		grep -Fqi 'sensitive plans' <<< "$$policy"; \
		! grep -Fqi 'read exact file contents through the GitHub' <<< "$$policy"; \
		grep -Fqx "  $$agent.md: |-" <<< "$$rendered"; \
		grep -Fqx "              - key: $$agent.md" <<< "$$rendered"; \
		grep -Fqx "                path: agents/$$agent.md" <<< "$$rendered"; \
	done; \
	grep -Fqx '  terra.md: |-' <<< "$$rendered"; \
	grep -Fqx "    description: Use for bounded generic coding, debugging, or repository tasks when the assigning primary agent's execution budget is nearing completion or it otherwise needs execution capacity; the primary retains task interpretation, safety, delivery decisions, and final synthesis" <<< "$$rendered"; \
	grep -Fqx '    mode: subagent' <<< "$$rendered"; \
	grep -Fqx '    model: openai/gpt-5.6-terra' <<< "$$rendered"; \
	grep -Fqx '    variant: default' <<< "$$rendered"; \
	grep -Fqx '              - key: terra.md' <<< "$$rendered"; \
	grep -Fqx '                path: agents/terra.md' <<< "$$rendered"; \
	archive_dir="$$(mktemp -d)"; \
	trap 'rm -rf "$$archive_dir"' EXIT; \
	helm package opencode-server --destination "$$archive_dir" > /dev/null; \
	archive="$$(find "$$archive_dir" -maxdepth 1 -type f -name 'opencode-server-0.2.1.tgz' -print -quit)"; \
	test -n "$$archive"; \
	archive_entries="$$(tar -tzf "$$archive")"; \
	archive_agents="$$all_agents terra"; \
	for agent in $$archive_agents; do \
		source="opencode-server/files/agents/$$agent.md"; \
		entry="opencode-server/files/agents/$$agent.md"; \
		grep -Fqx "$$entry" <<< "$$archive_entries"; \
		packaged="$$archive_dir/$$agent.md"; \
		tar -xOzf "$$archive" "$$entry" > "$$packaged"; \
		cmp -s "$$packaged" "$$source"; \
	done
