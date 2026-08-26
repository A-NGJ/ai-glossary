.PHONY: install-local

install-local:
	npx skills add "$(CURDIR)" -g -y \
		--skill ai-glossary-setup curate-glossary \
		--agent opencode
