SHELL := /bin/bash

COMPOSE_FILE := infra/docker-compose.yml

.PHONY: help up down logs ps health restart

help:
	@echo "Targets disponíveis:"
	@echo "  make up      -> sobe o Qdrant em background"
	@echo "  make down    -> derruba o Qdrant"
	@echo "  make logs    -> acompanha logs do Qdrant"
	@echo "  make ps      -> mostra status dos containers"
	@echo "  make health  -> verifica readiness do Qdrant"
	@echo "  make restart -> reinicia o Qdrant"

up:
	docker compose -f $(COMPOSE_FILE) up -d

down:
	docker compose -f $(COMPOSE_FILE) down

logs:
	docker compose -f $(COMPOSE_FILE) logs -f qdrant

ps:
	docker compose -f $(COMPOSE_FILE) ps

health:
	@curl -s http://localhost:6333/readyz

restart: down up
