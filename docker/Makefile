# Local Splunk dev harness for the Data Dictionary app.
# Requires Docker + docker compose. The app is bind-mounted from ../stage, so run
# `npm run build` from the repo root first (and again whenever JS/conf changes).

COMPOSE ?= docker compose
SERVICE  = splunk

.PHONY: up down restart logs port mgmt-port wait ps

up: ## Start Splunk (detached)
	$(COMPOSE) up -d

down: ## Stop and remove Splunk
	$(COMPOSE) down

restart: down up ## Recreate the container

ps: ## Show container status
	$(COMPOSE) ps

logs: ## Tail Splunk logs
	$(COMPOSE) logs -f $(SERVICE)

port: ## Print the Splunk Web URL (mapped host port for 8000)
	@PORT=$$($(COMPOSE) port $(SERVICE) 8000 | sed 's/.*://'); \
	echo "http://127.0.0.1:$$PORT"

mgmt-port: ## Print the mapped host port for the management API (8089)
	@$(COMPOSE) port $(SERVICE) 8089 | sed 's/.*://'

wait: ## Block until Splunk Web answers (up to ~3 min)
	@PORT=$$($(COMPOSE) port $(SERVICE) 8000 | sed 's/.*://'); \
	echo "Waiting for Splunk Web on http://127.0.0.1:$$PORT ..."; \
	for i in $$(seq 1 60); do \
	  CODE=$$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$$PORT/en-US/account/login" || true); \
	  if echo "$$CODE" | grep -qE '200|301|302|303'; then echo "Splunk is up ($$CODE)"; exit 0; fi; \
	  sleep 5; \
	done; \
	echo "Timed out waiting for Splunk"; exit 1
