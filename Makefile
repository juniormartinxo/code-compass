SHELL := /bin/bash

ifneq (,$(wildcard .env.local))
ENV_FILE ?= .env.local
else
ENV_FILE ?= .env
endif
COMPOSE_FILE ?= infra/docker-compose.yml
ifneq (,$(wildcard $(ENV_FILE)))
COMPOSE_ENV_FLAG := --env-file $(ENV_FILE)
endif
COMPOSE := docker compose $(COMPOSE_ENV_FLAG) -f $(COMPOSE_FILE)

QDRANT_HTTP_PORT ?= 6333
QDRANT_HEALTH_URL ?= http://localhost:$(QDRANT_HTTP_PORT)/readyz

INDEXER_DIR ?= apps/indexer
INDEXER_VENV ?= $(INDEXER_DIR)/.venv
INDEXER_PYTHON ?= python3
INDEXER_RUN_MODULE ?= indexer

MCP_SERVER_DIR ?= apps/mcp-server
INDEXER_DOCKER_PROFILE ?= indexer

.PHONY: help up down restart logs ps health wait-qdrant index index-full index-incremental index-docker index-docker-full index-docker-incremental setup-indexer ensure-indexer dev ensure-mcp-server index-all py-test py-lint py-typecheck py-setup acp-setup cli-setup

help:
	@echo "Targets disponíveis:"
	@echo "  make up                -> sobe o Qdrant e aguarda readiness"
	@echo "  make down              -> derruba o Qdrant"
	@echo "  make restart           -> reinicia o Qdrant"
	@echo "  make logs              -> acompanha logs do Qdrant"
	@echo "  make ps                -> mostra status dos containers"
	@echo "  make health            -> verifica readiness do Qdrant"
	@echo "  make index             -> indexação full (alias de index-full)"
	@echo "  make index-full        -> roda indexação full no apps/indexer"
	@echo "  make index-incremental -> fallback para indexação full (incremental ainda não implementado no CLI)"
	@echo "  make index-docker      -> indexação full via container (profile indexer)"
	@echo "  make index-docker-incremental -> fallback para indexação full via container"
	@echo "  make index-all         -> indexa todos os repos de code-base/"
	@echo "  make dev               -> sobe MCP server em modo dev"
	@echo "  make py-setup          -> instala deps Python (indexer/cli/acp)"
	@echo "  make py-test           -> roda pytest em apps Python"
	@echo "  make py-lint           -> roda lint Python (ruff)"
	@echo "  make py-typecheck      -> roda typecheck Python (mypy/pyright)"

up:
	$(COMPOSE) up -d qdrant
	$(MAKE) wait-qdrant

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f qdrant

ps:
	$(COMPOSE) ps

health:
	@curl -fsS $(QDRANT_HEALTH_URL)

wait-qdrant:
	@echo "Aguardando Qdrant ficar saudável em $(QDRANT_HEALTH_URL)..."
	@for attempt in $$(seq 1 30); do \
		if curl -fsS $(QDRANT_HEALTH_URL) >/dev/null; then \
			echo "Qdrant pronto."; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "Erro: timeout aguardando Qdrant em $(QDRANT_HEALTH_URL)."; \
	exit 1

index: index-full

index-docker: index-docker-full

index-full: ensure-indexer setup-indexer wait-qdrant
	cd $(INDEXER_DIR) && source .venv/bin/activate && PYTHONPATH=. python -m $(INDEXER_RUN_MODULE) index

index-incremental: ensure-indexer setup-indexer wait-qdrant
	@echo "Aviso: CLI atual não possui modo incremental dedicado; executando index completo."
	cd $(INDEXER_DIR) && source .venv/bin/activate && PYTHONPATH=. python -m $(INDEXER_RUN_MODULE) index

index-docker-full: wait-qdrant
	INDEXER_MODE=full $(COMPOSE) --profile $(INDEXER_DOCKER_PROFILE) run --rm indexer

index-docker-incremental: wait-qdrant
	@echo "Aviso: modo incremental ainda não implementado no container; executando index completo."
	INDEXER_MODE=incremental $(COMPOSE) --profile $(INDEXER_DOCKER_PROFILE) run --rm indexer

setup-indexer: ensure-indexer
	@if [ ! -d "$(INDEXER_VENV)" ]; then \
		echo "Criando virtualenv do indexer em $(INDEXER_VENV)..."; \
		$(INDEXER_PYTHON) -m venv $(INDEXER_VENV); \
	fi
	cd $(INDEXER_DIR) && source .venv/bin/activate && pip install --upgrade pip
	@if [ -f "$(INDEXER_DIR)/requirements.txt" ]; then \
		cd $(INDEXER_DIR) && source .venv/bin/activate && pip install -r requirements.txt; \
	elif [ -f "$(INDEXER_DIR)/pyproject.toml" ]; then \
		cd $(INDEXER_DIR) && source .venv/bin/activate && pip install -e .; \
	else \
		echo "Aviso: nenhum requirements.txt/pyproject.toml em $(INDEXER_DIR)."; \
	fi

ensure-indexer:
	@if [ ! -d "$(INDEXER_DIR)" ]; then \
		echo "Erro: diretório $(INDEXER_DIR) não encontrado."; \
		echo "Crie o indexer em apps/indexer ou ajuste INDEXER_DIR."; \
		exit 1; \
	fi

index-all: ensure-indexer setup-indexer wait-qdrant
	@./scripts/index-all.sh

dev: ensure-mcp-server
	cd $(MCP_SERVER_DIR) && npm install && npm run dev

ensure-mcp-server:
	@if [ ! -d "$(MCP_SERVER_DIR)" ]; then \
		echo "Erro: diretório $(MCP_SERVER_DIR) não encontrado."; \
		echo "Crie o MCP server em apps/mcp-server para usar make dev."; \
		exit 1; \
	fi

py-setup: setup-indexer cli-setup acp-setup

acp-setup:
	@if [ -d "apps/acp" ]; then \
		if [ ! -d "apps/acp/.venv" ]; then \
			echo "Criando virtualenv do ACP em apps/acp/.venv..."; \
			python3 -m venv apps/acp/.venv; \
		fi; \
		cd apps/acp && source .venv/bin/activate && pip install --upgrade pip; \
		if [ -f "apps/acp/requirements.txt" ]; then \
			cd apps/acp && source .venv/bin/activate && pip install -r requirements.txt; \
		else \
			cd apps/acp && source .venv/bin/activate && pip install -e .; \
		fi; \
	else \
		echo "Aviso: apps/acp não encontrado; pulando."; \
	fi

cli-setup:
	@if [ -d "apps/cli" ]; then \
		if [ ! -d "apps/cli/.venv" ]; then \
			echo "Criando virtualenv do CLI em apps/cli/.venv..."; \
			python3 -m venv apps/cli/.venv; \
		fi; \
		cd apps/cli && source .venv/bin/activate && pip install --upgrade pip; \
		if [ -f "apps/cli/requirements.txt" ]; then \
			cd apps/cli && source .venv/bin/activate && pip install -r requirements.txt; \
		else \
			cd apps/cli && source .venv/bin/activate && pip install -e .; \
		fi; \
	else \
		echo "Aviso: apps/cli não encontrado; pulando."; \
	fi

py-test:
	@$(MAKE) py-setup
	@for dir in apps/indexer apps/cli apps/acp; do \
		if [ -d "$$dir" ]; then \
			if [ -x "$$dir/.venv/bin/python" ]; then \
				if [ -d "$$dir/tests" ]; then \
					echo "Rodando pytest em $$dir..."; \
					cd $$dir && .venv/bin/python -m pytest tests -v; \
				else \
					echo "Aviso: $$dir não possui pasta tests; pulando."; \
				fi; \
			else \
				echo "Aviso: $$dir sem venv; rode make py-setup."; \
			fi; \
		fi; \
	done

py-lint:
	@for dir in apps/indexer apps/cli apps/acp; do \
		if [ -d "$$dir" ]; then \
			if [ -x "$$dir/.venv/bin/python" ] && [ -x "$$dir/.venv/bin/ruff" ]; then \
				echo "Rodando ruff em $$dir..."; \
				cd $$dir && .venv/bin/ruff check .; \
			else \
				echo "Aviso: ruff não encontrado em $$dir/.venv/bin"; \
			fi; \
		fi; \
	done

py-typecheck:
	@for dir in apps/indexer apps/cli apps/acp; do \
		if [ -d "$$dir" ]; then \
			if [ -x "$$dir/.venv/bin/python" ]; then \
				if [ -x "$$dir/.venv/bin/mypy" ]; then \
					echo "Rodando mypy em $$dir..."; \
					cd $$dir && .venv/bin/mypy .; \
				elif [ -x "$$dir/.venv/bin/pyright" ]; then \
					echo "Rodando pyright em $$dir..."; \
					cd $$dir && .venv/bin/pyright; \
				else \
					echo "Aviso: mypy/pyright não encontrado em $$dir/.venv/bin"; \
				fi; \
			fi; \
		fi; \
	done
