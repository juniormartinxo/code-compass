# Plano Atualizado: Google ADK com Memória Local em SQLite + Qdrant Opcional

## Resumo

Migrar o `apps/acp` para Google ADK com substituição direta do `agent.py`, preservando interface ACP/CLI atual, mantendo Qdrant para busca técnica e adotando memória de longo prazo híbrida:

1. `local`: SQLite como source of truth da memória + índice semântico opcional em Qdrant.
2. `cloud`: `VertexAiSessionService` + `VertexAiMemoryBankService`.
3. Identidade multiusuário em servidor de internet via `set_config_option` por sessão, sem fallback para usuário do SO.

## Contratos Públicos e Interfaces

1. Contratos ACP/CLI preservados:
   - `initialize`, `new_session`, `prompt`, `cancel` continuam iguais.
   - Slash commands atuais continuam (`/repo`, `/config`, `/model`, `/grounded`, `/knowledge`, `/content-type`).

2. Novas env vars:
   - `AGENT_RUNTIME_MODE=local|cloud` (default `local`).
   - `PROJECT_ID`, `LOCATION`, `AGENT_ENGINE_ID` (obrigatórias só em `cloud`).
   - `CODE_COMPASS_USER_ID` (default para dev/local single-user).
   - `ACP_MEMORY_DB_PATH` (default `apps/acp/.data/memory.sqlite3`).
   - `ACP_MEMORY_QDRANT_INDEX_ENABLED=true|false` (default `false`).
   - `ACP_MEMORY_QDRANT_COLLECTION` (default `compass_memory_local`).
   - `ACP_DISABLE_OS_USER_FALLBACK=true|false` (default `false` local, `true` cloud).

3. Nova interface de configuração por sessão (ACP):
   - Implementar `set_config_option` no agente para aceitar:
   `user.id`, `user.tenant`, `memory.long_term.enabled`.
   - Uso esperado em servidor internet: gateway autenticador seta `user.id` e `user.tenant` logo após `new_session`.

4. `/config` expandido:

   - Exibir `runtimeMode`, `memoryBackend`, `memoryIndexBackend`, `userIdentitySource`, `longTermMemoryEnabled`, `memoryHealth`.

## Arquitetura Alvo

1. Runtime `local`:
   - Orquestração ADK (`Agent` + `Runner.run_async`).
   - Histórico imediato com session service local/in-memory.
   - Memória longa em SQLite.
   - Qdrant opcional só para recuperação semântica da memória.

2. Runtime `cloud`:
   - Orquestração ADK.
   - `VertexAiSessionService` para histórico imediato.
   - `VertexAiMemoryBankService` para memória longa.
   - Sem `user_id` autenticado válido: apenas memória de sessão.

3. Busca técnica:
   - Não remover Qdrant.
   - Implementar Custom Tool ADK para busca no código reutilizando lógica Python do indexer (`embedder` + `qdrant_store`).

## Implementação (Arquivo a Arquivo)

1. Dependências ACP:
   - Atualizar [apps/acp/pyproject.toml](/home/junior/apps/jm/code-compass/apps/acp/pyproject.toml).
   - Adicionar `google-adk[vertexai]`, `qdrant-client`, `httpx`.

2. Substituição direta do motor:
   - Refatorar [apps/acp/src/code_compass_acp/agent.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/agent.py) para ADK.
   - Remover dependência da orquestração por `McpBridge.ask_code` no caminho principal.
   - Manter comportamento de streaming para ACP via eventos do `Runner.run_async`.

3. Builder do agente ADK:
   - Criar [apps/acp/src/code_compass_acp/adk_agent_builder.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/adk_agent_builder.py).
   - `instruction`: “Navegador técnico, direto, humor sagaz, focado em clareza arquitetural”.
   - Tools padrão: `PreloadMemoryTool` + `search_code_qdrant_tool`.
   - Regras de decisão na instruction: usar busca de código para dúvida técnica; usar memória para preferências/fatos do usuário.

4. Runtime services:
   - Criar [apps/acp/src/code_compass_acp/adk_runtime.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/adk_runtime.py).
   - Resolver runtime (`local`/`cloud`), montar `Runner`, session service e memory service adequados.
   - Validar envs obrigatórias em `cloud`.

5. Memória local SQLite (source of truth):
   - Criar [apps/acp/src/code_compass_acp/memory/local_sqlite_store.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/local_sqlite_store.py).
   - Schema:
   `memory_entries(id, user_id, tenant_id, kind, topic, value, confidence, created_at, updated_at, source_session_id, active)`.
   - Índices:
   `(user_id, active)`, `(user_id, kind, topic)`, `(updated_at)`.
   - Upsert deduplicado por `(user_id, kind, topic, value_hash)`.

6. Índice semântico opcional da memória no Qdrant:
   - Criar [apps/acp/src/code_compass_acp/memory/local_memory_qdrant_index.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/local_memory_qdrant_index.py).
   - Quando habilitado, sincronizar entradas ativas do SQLite para collection de memória.
   - Busca de memória:
   primeiro candidatos semânticos no Qdrant, depois hydrate/filtra no SQLite.
   - Quando desabilitado, retrieval apenas por consulta estruturada no SQLite.

7. Memory service unificada:
   - Criar [apps/acp/src/code_compass_acp/memory/memory_service.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/memory_service.py).
   - Interface única usada por `PreloadMemoryTool` e callbacks.
   - Implementações:
   `LocalMemoryService(SQLite + Qdrant opcional)` e `CloudMemoryService(Vertex Memory Bank)`.

8. Extração assíncrona de fatos/preferências:
   - Criar [apps/acp/src/code_compass_acp/memory/memory_extractor.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/memory_extractor.py).
   - Integrar em `after_agent_callback`.
   - Extrair só fatos/preferências técnicas: stack favorita/rejeitada, padrões de nomenclatura, decisões de design.
   - Escrita assíncrona sem bloquear resposta.

9. Tool de busca técnica:
   - Criar [apps/acp/src/code_compass_acp/tools/search_code_qdrant_tool.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/tools/search_code_qdrant_tool.py).
   - Reuso da lógica já existente em `apps/indexer/indexer/embedder.py` e `apps/indexer/indexer/qdrant_store.py`.
   - Saída padronizada com `repo/path/startLine/endLine/snippet/score/contentType`.

10. Identidade multiusuário:
    - Em `set_config_option`, aceitar `user.id` e `user.tenant`.
    - Resolver `memory_user_id` como `sha256(tenant + ":" + user.id)` para cloud/internet.
    - Em `local` dev, fallback para `CODE_COMPASS_USER_ID`, depois `$USER` se permitido.

11. Bootstrap/documentação:
    - Ajustar [bin/dev-chat](/home/junior/apps/jm/code-compass/bin/dev-chat) para modo ADK sem exigir Vertex no local.
    - Atualizar [.env.example](/home/junior/apps/jm/code-compass/.env.example), [apps/acp/README.md](/home/junior/apps/jm/code-compass/apps/acp/README.md), [apps/docs/pages/acp-agent.md](/home/junior/apps/jm/code-compass/apps/docs/pages/acp-agent.md).

## Testes e Cenários de Aceitação

1. Regressão ACP:
   - sessão, prompt, cancel, streaming e slash commands sem quebra.

2. Runtime:
   - `local` sobe sem env Vertex.
   - `cloud` valida env Vertex obrigatória.

3. Memória local SQLite:
   - persiste preferência entre reinícios de processo.
   - update/deduplicação funciona.
   - desativação lógica (`active=false`) remove da recuperação.

4. Memória local com Qdrant opcional:
   - com flag `false`, retrieval funciona só via SQLite.
   - com flag `true`, retrieval semântico retorna candidatos corretos e sem vazamento entre usuários.

5. Memória cloud:
   - com `user.id`/`tenant`, persiste e recupera em sessão futura.
   - sem identidade autenticada, não grava memória longa.

6. Cenário funcional pedido:
   - conversa A: “odeio Redux”.
   - conversa B (depois, mesmo usuário): agente lembra a preferência no local (SQLite) e no cloud (Memory Bank).

7. Busca técnica:
   - tool ADK de código retorna evidências equivalentes ao comportamento atual de RAG técnico.

8. Comandos de validação:
   - `make py-setup`
   - `cd apps/acp && .venv/bin/python -m pytest tests -v`
   - `apps/acp/.venv/bin/python apps/acp/scripts/e2e_smoke.py`

## Rollout e Rollback

1. Rollout:
   - Deploy com `AGENT_RUNTIME_MODE=local` primeiro.
   - Validar memória local e busca técnica.
   - Depois habilitar `cloud` em ambiente com identidade autenticada por sessão.

2. Rollback:
   - Revert único do `apps/acp` para commit anterior ao ADK.
   - Sem migração destrutiva de contratos MCP/CLI.

## Assunções e Defaults

1. Google ADK é obrigatório como framework de orquestração.
2. `local` usa SQLite como memória longa padrão.
3. Qdrant para memória local é opcional e desligado por padrão.
4. `cloud` usa Vertex Session + Memory Bank.
5. Em servidor internet, identidade vem de sessão autenticada (`set_config_option`) e não de usuário do SO.
6. Extração de memória grava apenas fatos/preferências técnicas.
