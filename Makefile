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
	@rendered="$$(helm template test opencode-server)"; \
	echo "$$rendered" | grep -Fqx '  terra.md: |-'; \
	echo "$$rendered" | grep -Fqx '    mode: subagent'; \
	echo "$$rendered" | grep -Fqx '    model: openai/gpt-5.6-terra'; \
	echo "$$rendered" | grep -Fqx '    variant: default'; \
	echo "$$rendered" | grep -Fqx '              - key: terra.md'; \
	echo "$$rendered" | grep -Fqx '                path: agents/terra.md'; \
	archive_dir="$$(mktemp -d)"; \
	trap 'rm -rf "$$archive_dir"' EXIT; \
	helm package opencode-server --destination "$$archive_dir" > /dev/null; \
	tar -tzf "$$archive_dir/opencode-server-0.2.0.tgz" | grep -Fqx 'opencode-server/files/agents/terra.md'
