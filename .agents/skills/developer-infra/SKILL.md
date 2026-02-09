---
name: developer-infra
description: Planejar e implementar mudanças de infraestrutura local e operacional (docker-compose, env vars, make targets, bootstrap, logs e métricas) para o Code Compass; usar quando o pedido tocar execução/observabilidade e não usar para lógica de MCP, indexação, modelagem vetorial ou documentação editorial.
---

# Developer Infra

## 1) Objetivo e Escopo
Manter o ambiente local e operacional reproduzível, observável e simples de inicializar do zero para desenvolvimento e validação.

### Trigger policy
- Disparar quando o pedido mencionar `infra/docker-compose.yml`, `.env`, `Makefile`, bootstrap local, saúde de serviços, logs/métricas ou troubleshooting operacional.
- Disparar quando houver mudança em porta, variável de ambiente, ordem de subida, readiness/liveness ou runbook de operação.
- Não disparar para implementação de tools MCP (`developer-mcp-server`), lógica de indexação (`developer-indexer`), schema Qdrant (`developer-vector-db`) ou edição de documentação ampla (`developer-docs`).

## 2) Entradas esperadas
- Ambiente alvo (local dev, CI, staging) e sistema operacional relevante.
- Lista de serviços e dependências (MCP server, indexer, Qdrant).
- Variáveis de ambiente obrigatórias/ opcionais e valores padrão.
- Meta operacional (tempo de bootstrap, observabilidade mínima, comandos únicos de operação).

## 3) Workflow (Discovery -> Plan -> Implement -> Validate -> Deliver)
1. Discovery
   - Mapear `infra/`, `Makefile`, scripts de bootstrap e variáveis em `.env.example`.
   - Identificar pré-requisitos, dependências cíclicas e pontos frágeis de inicialização.
   - Consultar `references/checklist.md` para baseline de operação.
2. Plan
   - Definir passos de mudança com impacto em dev/CI e estratégia de rollback.
   - Explicitar variações por ambiente e riscos de compatibilidade.
3. Implement
   - Aplicar mudanças mínimas em compose/env/make targets.
   - Padronizar comandos de subir, derrubar, logs e limpeza com nomenclatura estável.
   - Ajustar observabilidade mínima (healthcheck, logs úteis, métricas quando aplicável).
4. Validate
   - Executar fluxo "do zero" até serviço saudável.
   - Validar comandos principais (`up`, `down`, `logs`, `index`, `dev`) e falhas comuns.
5. Deliver
   - Entregar plano executado, alterações por arquivo, comandos de verificação e passos de rollback.

## 4) DoD
- Bootstrap local funciona do zero com instruções claras e reproduzíveis.
- Variáveis obrigatórias estão documentadas e com defaults seguros quando possível.
- Compose e targets cobrem ciclo mínimo de operação (subir, logs, parar, limpar).
- Logs/healthcheck permitem diagnóstico rápido de falhas.
- Mudanças não quebram fluxo existente sem nota explícita de migração.

## 5) Guardrails
- Não comitar segredos; usar placeholders e variáveis de ambiente.
- Não alterar portas/nomes de serviço sem atualizar referências dependentes.
- Não introduzir dependências pesadas sem necessidade operacional clara.
- Não remover comandos existentes sem alternativa equivalente.
- Não criar `scripts/` nesta skill sem necessidade determinística comprovada.

## 6) Convenções de saída
- Sempre devolver: (1) plano, (2) mudanças por arquivo, (3) comandos para reproduzir, (4) rollback e riscos.
- Sempre explicitar pré-requisitos, variáveis obrigatórias e comportamento esperado após cada comando.

## 7) Exemplos de uso (prompts)
- "Padronize o `docker-compose` para subir Qdrant e validar healthcheck automaticamente."
- "Revise `.env.example` e o Makefile para permitir boot completo com `make up`, `make index` e `make dev`."
- "Adicione observabilidade básica (logs e métricas) para diagnosticar falhas no pipeline local."
- "Faça um fluxo de bootstrap do zero para novo dev com o menor número de passos possível."

## 8) Anti-exemplos (quando não usar)
- "Criar nova tool MCP no NestJS" -> usar `developer-mcp-server`.
- "Mudar estratégia de chunking/embedding" -> usar `developer-indexer`.
- "Migrar schema de collection no Qdrant" -> usar `developer-vector-db`.
- "Escrever ADR e quickstart em linguagem mais didática" -> usar `developer-docs`.
