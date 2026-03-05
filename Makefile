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
CLI_PYTHON ?= python3.14

MCP_SERVER_DIR ?= apps/mcp-server
INDEXER_DOCKER_PROFILE ?= indexer

.PHONY: help up down restart logs ps health wait-qdrant index index-full index-incremental index-docker index-docker-full index-docker-incremental setup-indexer ensure-indexer dev ensure-mcp-server index-all py-test py-lint py-typecheck py-setup acp-setup cli-setup chat-setup chat

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
	@echo "  make chat-setup        -> prepara infra + CLI/ACP + build MCP para chat"
	@echo "  make chat              -> prepara ambiente e abre o chat no terminal"
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
	cd $(INDEXER_DIR) && PYTHONPATH=. .venv/bin/python -m $(INDEXER_RUN_MODULE) index

index-incremental: ensure-indexer setup-indexer wait-qdrant
	@echo "Aviso: CLI atual não possui modo incremental dedicado; executando index completo."
	cd $(INDEXER_DIR) && PYTHONPATH=. .venv/bin/python -m $(INDEXER_RUN_MODULE) index

index-docker-full: wait-qdrant
	INDEXER_MODE=full $(COMPOSE) --profile $(INDEXER_DOCKER_PROFILE) run --rm indexer

index-docker-incremental: wait-qdrant
	@echo "Aviso: modo incremental ainda não implementado no container; executando index completo."
	INDEXER_MODE=incremental $(COMPOSE) --profile $(INDEXER_DOCKER_PROFILE) run --rm indexer

setup-indexer: ensure-indexer
	@EXPECTED_VENV="$(abspath $(INDEXER_VENV))"; \
	if [ ! -d "$(INDEXER_VENV)" ]; then \
		echo "Criando virtualenv do indexer em $(INDEXER_VENV)..."; \
		$(INDEXER_PYTHON) -m venv "$(INDEXER_VENV)"; \
	elif ! grep -Fq "$$EXPECTED_VENV" "$(INDEXER_VENV)/bin/activate" 2>/dev/null; then \
		echo "Recriando virtualenv do indexer em $(INDEXER_VENV) (path antigo detectado)..."; \
		$(INDEXER_PYTHON) -m venv --clear "$(INDEXER_VENV)"; \
	fi
	cd $(INDEXER_DIR) && .venv/bin/python -m pip install --upgrade pip
	@if [ -f "$(INDEXER_DIR)/requirements.txt" ]; then \
		cd $(INDEXER_DIR) && .venv/bin/python -m pip install -r requirements.txt; \
	elif [ -f "$(INDEXER_DIR)/pyproject.toml" ]; then \
		cd $(INDEXER_DIR) && .venv/bin/python -m pip install -e .; \
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

chat-setup: up cli-setup acp-setup ensure-mcp-server
	@if [ ! -d "$(MCP_SERVER_DIR)/node_modules" ]; then \
		echo "Instalando dependências do MCP server..."; \
		pnpm -C $(MCP_SERVER_DIR) install; \
	fi
	@echo "Buildando MCP server..."
	pnpm -C $(MCP_SERVER_DIR) run build

chat: chat-setup
	pnpm chat

ensure-mcp-server:
	@if [ ! -d "$(MCP_SERVER_DIR)" ]; then \
		echo "Erro: diretório $(MCP_SERVER_DIR) não encontrado."; \
		echo "Crie o MCP server em apps/mcp-server para usar make dev."; \
		exit 1; \
	fi

py-setup: setup-indexer cli-setup acp-setup

acp-setup:
	@if [ -d "apps/acp" ]; then \
		EXPECTED_VENV="$(abspath apps/acp/.venv)"; \
		if [ ! -d "apps/acp/.venv" ]; then \
			echo "Criando virtualenv do ACP em apps/acp/.venv..."; \
			python3 -m venv apps/acp/.venv; \
		elif ! grep -Fq "$$EXPECTED_VENV" "apps/acp/.venv/bin/activate" 2>/dev/null; then \
			echo "Recriando virtualenv do ACP em apps/acp/.venv (path antigo detectado)..."; \
			python3 -m venv --clear apps/acp/.venv; \
		fi; \
		cd apps/acp && .venv/bin/python -m pip install --upgrade pip; \
		if [ -f "requirements.txt" ]; then \
			.venv/bin/python -m pip install -r requirements.txt; \
		else \
			.venv/bin/python -m pip install -e .; \
		fi; \
	else \
		echo "Aviso: apps/acp não encontrado; pulando."; \
	fi

cli-setup:
	@if [ -d "apps/cli" ]; then \
		CLI_BOOTSTRAP_PY="$(CLI_PYTHON)"; \
		if ! command -v "$$CLI_BOOTSTRAP_PY" >/dev/null 2>&1; then \
			echo "Aviso: $$CLI_BOOTSTRAP_PY não encontrado; usando python3 para a CLI."; \
			CLI_BOOTSTRAP_PY="python3"; \
		fi; \
		TARGET_PY_MM=$$($$CLI_BOOTSTRAP_PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'); \
		TOAD_COMPAT=$$($$CLI_BOOTSTRAP_PY -c 'import sys; print(int(sys.version_info >= (3, 14)))'); \
		CURRENT_PY_MM=""; \
		if [ -x "apps/cli/.venv/bin/python" ]; then \
			CURRENT_PY_MM=$$(apps/cli/.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true); \
		fi; \
		EXPECTED_VENV="$(abspath apps/cli/.venv)"; \
		if [ ! -d "apps/cli/.venv" ]; then \
			echo "Criando virtualenv do CLI em apps/cli/.venv com $$CLI_BOOTSTRAP_PY..."; \
			$$CLI_BOOTSTRAP_PY -m venv apps/cli/.venv; \
		elif ! grep -Fq "$$EXPECTED_VENV" "apps/cli/.venv/bin/activate" 2>/dev/null; then \
			echo "Recriando virtualenv do CLI em apps/cli/.venv com $$CLI_BOOTSTRAP_PY (path antigo detectado)..."; \
			$$CLI_BOOTSTRAP_PY -m venv --clear apps/cli/.venv; \
		elif [ -z "$$CURRENT_PY_MM" ]; then \
			echo "Recriando virtualenv do CLI em apps/cli/.venv (venv inválida detectada)..."; \
			$$CLI_BOOTSTRAP_PY -m venv --clear apps/cli/.venv; \
		elif [ "$$CURRENT_PY_MM" != "$$TARGET_PY_MM" ]; then \
			echo "Recriando virtualenv do CLI em apps/cli/.venv (Python $$CURRENT_PY_MM -> $$TARGET_PY_MM)..."; \
			$$CLI_BOOTSTRAP_PY -m venv --clear apps/cli/.venv; \
		fi; \
		if [ "$$TOAD_COMPAT" != "1" ]; then \
			echo "Aviso: $$CLI_BOOTSTRAP_PY resolve para Python $$TARGET_PY_MM (< 3.14). O comando 'chat' exige toad em Python >= 3.14."; \
		fi; \
		cd apps/cli && .venv/bin/python -m pip install --upgrade pip; \
		if [ -f "requirements.txt" ]; then \
			.venv/bin/python -m pip install -r requirements.txt; \
		else \
			.venv/bin/python -m pip install -e .; \
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
