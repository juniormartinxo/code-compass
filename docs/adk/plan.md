# Plano Atualizado: Google ADK com Memória Local em SQLite + Qdrant Opcional

## Resumo

Evoluir o `apps/acp` para Google ADK com adaptação controlada do motor atual, preservando contratos ACP/CLI e mantendo o núcleo do Code Compass como retrieval técnico de codebase.

1. ADK fica restrito à camada de runtime/orquestração/memória; a busca técnica em Qdrant continua como eixo principal do produto.
2. `local`: SQLite é source of truth para memória longa e também para sessão persistente por padrão; Qdrant é opcional para shortlist semântico.
3. `cloud`: `VertexAiSessionService` + `VertexAiMemoryBankService`, com identidade autenticada obrigatória para memória longa.
4. Governança de memória com comandos `/memory`, transparência de origem/status, regras explícitas de conflito semântico e decay configurável em runtime.

## Contratos Públicos e Interfaces

1. Contratos ACP/CLI preservados:
   - `initialize`, `new_session`, `prompt`, `cancel` sem breaking change.
   - Slash commands atuais preservados: `/repo`, `/config`, `/model`, `/grounded`, `/knowledge`, `/content-type`.

2. Novos slash commands de memória:
   - Obrigatórios:
   - `/memory list`
   - `/memory forget <termo>`
   - `/memory clear`
   - `/memory enable`
   - `/memory disable`
   - Desejáveis:
   - `/memory why <id|termo>`
   - `/memory confirm <id>`
   - Objetivo: transparência, depuração e correção manual de memória sem intervenção operacional.

3. `set_config_option` por sessão:
   - Chaves obrigatórias:
   - `user.id`
   - `user.tenant`
   - `memory.long_term.enabled`
   - `memory.scope.mode` com valores `session|user`
   - Chave complementar para isolamento explícito por aplicação/ambiente:
   - `app.name` (fallback para env `ACP_APP_NAME`)
   - Regras:
   - `memory.long_term.enabled=false` impede gravação de memória longa.
   - Em `cloud`, sem identidade autenticada válida (`user.id` + `user.tenant`), memória longa é bloqueada mesmo se habilitada.
   - `memory.scope.mode=session` limita a memória persistida e recuperada àquela sessão específica, com retenção local apenas para continuidade e auditoria, sem reaproveitamento cross-session.
   - `memory.scope.mode=user` permite reaproveitamento de memória entre sessões do mesmo usuário, respeitando `app_name + environment + tenant_id`.

4. Expansão de `/config`:
   - Exibir `runtimeMode`, `memoryBackend`, `sessionBackend`, `memoryIndexBackend`, `appName`, `userIdentitySource`, `memoryScopeMode`, `longTermMemoryEnabled`, `memoryHealth`.

5. Variáveis de ambiente:
   - `AGENT_RUNTIME_MODE=local|cloud` (default `local`).
   - `PROJECT_ID`, `LOCATION`, `AGENT_ENGINE_ID` (obrigatórias em `cloud`).
   - `ACP_APP_NAME` (default `code-compass`).
   - `ACP_ENVIRONMENT` (default `local`).
   - `CODE_COMPASS_USER_ID` (uso local/single-user).
   - `ACP_MEMORY_DB_PATH` (default `apps/acp/.data/memory.sqlite3`).
   - `ACP_SESSION_DB_PATH` (default igual a `ACP_MEMORY_DB_PATH`).
   - `ACP_SESSION_BACKEND=sqlite|memory` (default `sqlite` em `local`; `memory` apenas fallback secundário).
   - `ACP_MEMORY_QDRANT_INDEX_ENABLED=true|false` (default `false`).
   - `ACP_MEMORY_QDRANT_COLLECTION` (default `compass_memory_local`).
   - `ACP_DISABLE_OS_USER_FALLBACK=true|false` (default `false` local, `true` cloud).
   - `ACP_MEMORY_MIN_CONFIDENCE` (default inicial `0.7`).
   - `ACP_MEMORY_SIMILARITY_MODE=lexical|semantic` (default inicial `lexical` durante rollout local).
   - `ACP_MEMORY_SIMILARITY_HIGH` (default inicial `0.60` em `lexical`; `0.92` em `semantic`).
   - `ACP_MEMORY_SIMILARITY_MEDIUM` (default inicial `0.30` em `lexical`; `0.78` em `semantic`).
   - `ACP_PRELOAD_MEMORY_MAX_ENTRIES` (default `20`).
   - `ACP_PRELOAD_MEMORY_MAX_TOKENS` (default `1500`).

## Arquitetura Alvo

1. Guardrails arquiteturais ADK:
   - ADK é obrigatório para runtime/orquestração/memória.
   - O núcleo continua sendo retrieval técnico da codebase.
   - Evitar acoplamento espalhado ao ADK fora de runtime/builder/services.
   - `agent.py` atua como fachada de compatibilidade ACP, sem concentrar regra de negócio de memória/retrieval.

2. Runtime `local`:
   - `Runner.run_async` do ADK para execução.
   - Sessão persistida em SQLite por padrão para previsibilidade, debug, reinício de processo e testes.
   - Memória longa em SQLite como source of truth.
   - Qdrant opcional apenas para shortlist semântico de memória.

3. Runtime `cloud`:
   - `VertexAiSessionService` para sessão imediata.
   - `VertexAiMemoryBankService` para memória longa.
   - Sem identidade autenticada válida, operar só com memória de sessão (sem escrita longa).

4. Busca técnica:
   - Qdrant de código permanece obrigatório no fluxo de retrieval técnico.
   - Tool ADK de busca técnica reutiliza `apps/indexer/indexer/embedder.py` e `apps/indexer/indexer/qdrant_store.py`.

## Modelo de Dados de Memória (Persistido x Derivado)

1. Tabela `memory_entries` (SQLite, persistido):
   - `id`
   - `app_name`
   - `environment`
   - `tenant_id`
   - `user_id`
   - `scope_mode` (`session|user`)
   - `scope_id` (`session_id` quando `scope_mode=session`, senão `memory_user_id`)
   - `kind`
   - `topic`
   - `value`
   - `value_hash`
   - `confidence` (valor bruto original, imutável após criação)
   - `last_confirmed_at`
   - `times_reinforced`
   - `source_session_id`
   - `active`
   - `supersedes_entry_id`
   - `created_at`
   - `updated_at`
   - `disabled_at` (opcional)
   - `disabled_reason` (opcional)
   - `metadata_json` (opcional)

2. Índices mínimos:
   - `(app_name, environment, tenant_id, user_id, active)`
   - `(app_name, environment, tenant_id, user_id, kind, topic)`
   - `(app_name, environment, tenant_id, scope_mode, scope_id, active)`
   - `(updated_at)`
   - Guardrail de consulta: `scope_id` nunca deve ser consultado isoladamente; sempre com filtro conjunto de `app_name + environment + tenant_id`.

3. Tabela de sessão local persistente:
   - `session_turns(id, app_name, environment, tenant_id, memory_user_id, session_id, role, content, created_at, turn_index)`.
   - `tenant_id` e `memory_user_id` devem ser preenchidos quando disponíveis para suportar investigação e limpeza operacional sem depender apenas de `session_id`.
   - Índices operacionais:
   - `(app_name, environment, session_id, turn_index)`
   - `(app_name, environment, tenant_id, memory_user_id, created_at)`
   - Em `local`, é o backend default de histórico imediato.

4. Campos derivados em runtime (não persistidos como verdade final):
   - `effective_confidence`: calculado em retrieval.
   - `status` para `/memory why`:
   - `active` quando `active=true`
   - `superseded` quando `active=false` e substituída por outra entrada
   - `disabled` quando `active=false` por ação manual (`forget`/`clear`/`disable`)
   - Se existir score auxiliar persistido, ele é apenas cache e não substitui `confidence` bruto nem o cálculo final em runtime.

## Estratégia de Decay e Conflito Semântico

1. Decay de memória:
   - Não apagar automaticamente por idade.
   - Penalizar no retrieval via `effective_confidence`.
   - Fórmula inicial calibrável por testes:
   - `effective_confidence = confidence * exp(-lambda_kind * age_days) * reinforcement_factor`
   - `reinforcement_factor` cresce com `times_reinforced` com teto configurável.
   - Taxas iniciais (`lambda_kind`) configuráveis:
   - preferências/opiniões técnicas (`kind=preference|opinion`): decay forte.
   - convenções/decisões recorrentes (`kind=convention|decision`): decay moderado.
   - fatos estáveis (`kind=fact|profile`): decay fraco.

2. Resolução de conflito:
   - Dedupe por hash não é suficiente.
   - Para entradas do mesmo `app_name + environment + tenant_id + user_id + kind + topic`, usar similaridade semântica com thresholds configuráveis:
   - `ACP_MEMORY_SIMILARITY_MODE=lexical`: fallback com token/Jaccard e defaults `HIGH=0.60`, `MEDIUM=0.30` para operação local sem embeddings de memória.
   - `ACP_MEMORY_SIMILARITY_MODE=semantic`: uso de embeddings com defaults iniciais `HIGH=0.92`, `MEDIUM=0.78`.
   - Similaridade alta (`>= ACP_MEMORY_SIMILARITY_HIGH`): classificar como reforço ou contradição conforme polaridade/intenção.
   - Similaridade intermediária (`>= ACP_MEMORY_SIMILARITY_MEDIUM` e `< HIGH`): classificar como complemento.
   - Similaridade baixa (`< MEDIUM`): nova entrada independente.
   - Reforço: manter entrada ativa, atualizar `last_confirmed_at` e incrementar `times_reinforced`.
   - Complemento: manter entradas ativas com contexto/escopo distinto.
   - Contradição forte: nova entrada ativa; anterior recebe `active=false`; nova entrada preenche `supersedes_entry_id` apontando a substituída.
   - Proibido simplificar para "similaridade alta => substitui" sem análise de conteúdo/intenção.
   - Valores numéricos são defaults iniciais e devem ser calibrados por testes reais.

## Retrieval da Memória Local

1. Fluxo padrão:
   - SQLite é source of truth e decisão final.
   - Se Qdrant de memória estiver habilitado: usar apenas para shortlist semântico.
   - Sempre hidratar candidatos no SQLite, validar escopo/estado e aplicar ranking final no SQLite.
   - Em consultas por escopo, `scope_id` só pode ser usado junto com `app_name + environment + tenant_id`.

2. Ordem de ranking final:
   1. `active = true`
   2. isolamento por `user_id + tenant_id + app_name + environment`
   3. `effective_confidence` calculado em runtime com decay
   4. similaridade semântica (quando Qdrant habilitado)
   5. recência (`last_confirmed_at` > `updated_at` > `created_at`)

3. Sem Qdrant:
   - Retrieval continua funcional por consulta estruturada no SQLite com os mesmos fatores, exceto similaridade semântica.

4. Comportamento equivalente em `cloud`:
   - `CloudMemoryService` aplica ranking equivalente usando metadados disponíveis do Memory Bank e fallback explícito quando campos não existirem, sem violar precedência de `active`, isolamento e recência.

## Implementação (Arquivo a Arquivo)

1. Dependências ACP:
   - Atualizar [apps/acp/pyproject.toml](/home/junior/apps/jm/code-compass/apps/acp/pyproject.toml) com `google-adk[vertexai]`, `qdrant-client`, `httpx`.

2. Fachada de compatibilidade ACP:
   - Refatorar [apps/acp/src/code_compass_acp/agent.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/agent.py).
   - Manter contratos ACP e streaming.
   - Delegar runtime/orquestração para módulos dedicados.
   - Implementar `set_config_option` com `user.id`, `user.tenant`, `memory.long_term.enabled`, `memory.scope.mode`, `app.name`.
   - Registrar e rotear comandos `/memory`.

3. Builder e runtime ADK:
   - Criar [apps/acp/src/code_compass_acp/adk_agent_builder.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/adk_agent_builder.py).
   - Criar [apps/acp/src/code_compass_acp/adk_runtime.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/adk_runtime.py).
   - Descrever migração como adaptação controlada: manter via feature flag temporária caminho legado de execução para rollback rápido.

4. Sessão local persistente:
   - Criar [apps/acp/src/code_compass_acp/memory/local_session_store.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/local_session_store.py).
   - Persistir histórico imediato em SQLite por padrão (`ACP_SESSION_BACKEND=sqlite`).
   - Persistir `app_name` e `environment` em todos os turnos; persistir `tenant_id` e `memory_user_id` quando disponíveis no contexto autenticado.
   - Criar índices de suporte para leitura por `session_id` e para investigação/limpeza por `app_name + environment + tenant_id + memory_user_id`.
   - Migração compatível: adicionar novas colunas como nullable e preencher obrigatoriamente apenas novos registros.
   - Manter backend `memory` apenas como fallback secundário.

5. Store SQLite de memória:
   - Criar [apps/acp/src/code_compass_acp/memory/local_sqlite_store.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/local_sqlite_store.py).
   - Implementar schema/índices acima.
   - Implementar cálculo de `memory_user_id = sha256(tenant + \":\" + user.id)` e chaves de isolamento por `app_name` e `environment`.
   - Documentar no código (comentário e validação de query builder) que `scope_id` não deve ser usado sem `app_name + environment + tenant_id` para evitar colisões entre tenants/ambientes.

6. Índice semântico opcional de memória:
   - Criar [apps/acp/src/code_compass_acp/memory/local_memory_qdrant_index.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/local_memory_qdrant_index.py).
   - Sincronizar apenas entradas ativas.
   - Nunca usar Qdrant como fonte final de verdade.

7. Decay e conflito:
   - Criar [apps/acp/src/code_compass_acp/memory/memory_decay.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/memory_decay.py).
   - Criar [apps/acp/src/code_compass_acp/memory/conflict_resolver.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/conflict_resolver.py).
   - Implementar classificação explícita: `reinforcement`, `complement`, `contradiction`.

8. Service de memória unificada:
   - Criar [apps/acp/src/code_compass_acp/memory/memory_service.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/memory_service.py).
   - Expor operações para:
      - preload e retrieval ranqueado
      - `list`, `forget`, `clear`, `enable`, `disable`, `why`, `confirm`
   - Implementar `LocalMemoryService` e `CloudMemoryService` com comportamento equivalente de ranking.

9. Extração de memória:
   - Criar [apps/acp/src/code_compass_acp/memory/memory_extractor.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/memory_extractor.py).
   - Extrair somente fatos/preferências técnicas de longo prazo.
   - Não extrair: contexto efêmero de ticket, conteúdo recuperável da codebase, detalhes transitórios da conversa.
   - Separar explicitamente contexto imediato de sessão (curto prazo) de memória longa do usuário.
   - Aplicar threshold `confidence >= 0.7` (configurável).
   - Aplicar dedupe e resolução de conflito semântico.
   - Em `cloud`, modo híbrido:
      - caminho prioritário: gravação explícita via SDK/API
      - caminho complementar: submissão de sessões concluídas ao Memory Bank
      - precedência: memória explícita > memória derivada automaticamente
      - reconciliação/deduplicação obrigatória para evitar duplicação entre fontes

10. Tools ADK:
    - Criar [apps/acp/src/code_compass_acp/tools/preload_memory_tool.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/tools/preload_memory_tool.py).
    - Default: no máximo 20 entradas e 1.500 tokens por sessão.
    - Seleção por maior `effective_confidence` e recência.
    - Limites existem para evitar degradação de qualidade do contexto em sessões longas e usuários com histórico extenso.
    - Entradas excedentes não são injetadas no contexto, mas permanecem no SQLite.
    - Criar [apps/acp/src/code_compass_acp/tools/search_code_qdrant_tool.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/tools/search_code_qdrant_tool.py) para retrieval técnico.

11. Comandos `/memory`:
    - Criar [apps/acp/src/code_compass_acp/memory/memory_commands.py](/home/junior/apps/jm/code-compass/apps/acp/src/code_compass_acp/memory/memory_commands.py).
    - Regras mínimas:
       - `/memory list`: lista entradas do usuário/escopo atual.
       - `/memory forget <termo>`: desativa entradas relacionadas.
       - `/memory clear`: desativa todas as entradas longas do usuário atual.
       - `/memory enable` e `/memory disable`: alternam gravação longa da sessão.
       - `/memory why <id|termo>`: exibe `source_session_id`, `status` e timestamps.
       - `/memory confirm <id>`: reforça entrada (`last_confirmed_at`, `times_reinforced`).

12. Bootstrap e documentação:
    - Ajustar [bin/dev-chat](/home/junior/apps/jm/code-compass/bin/dev-chat), [.env.example](/home/junior/apps/jm/code-compass/.env.example), [apps/acp/README.md](/home/junior/apps/jm/code-compass/apps/acp/README.md), [apps/docs/pages/acp-agent.md](/home/junior/apps/jm/code-compass/apps/docs/pages/acp-agent.md).

## Testes e Cenários de Aceitação

1. Regressão de contrato ACP/CLI:
   - `initialize`, `new_session`, `prompt`, `cancel`, streaming e slash commands existentes sem quebra.

2. Guardrails arquiteturais:
   - `agent.py` como fachada; lógica de runtime/builder/memory fora da fachada.
   - Busca técnica continua funcional e prioritária para perguntas de codebase.

3. Sessão local persistente:
   - Reinício de processo no modo `local` preserva histórico imediato via SQLite.
   - Consulta e limpeza operacional de sessões funcionam por `app_name + environment + tenant_id + memory_user_id`, sem depender apenas de `session_id`.
   - Fallback in-memory funciona quando explicitamente configurado.

4. Decay e ranking:
   - Memória antiga perde prioridade versus memória recente por `effective_confidence`.
   - `confidence` bruto permanece inalterado após retrieval.

5. Reforço de memória:
   - `/memory confirm <id>` e reforço automático atualizam `last_confirmed_at` e `times_reinforced`.

6. Conflitos semânticos:
   - Contradição forte desativa entrada anterior e preenche `supersedes_entry_id`.
   - Complemento mantém ambas as entradas ativas.
   - Reforço não cria substituição indevida.

7. Governança `/memory`:
   - `/memory list`, `/memory forget`, `/memory clear`, `/memory enable`, `/memory disable` validados.
   - `/memory why` retorna `source_session_id`, `status` e timestamps.

8. Isolamento multiusuário e multi-tenant:
   - Mesmo `user.id` em tenants diferentes sem vazamento cruzado.
   - Isolamento adicional por `app_name` e `environment`.

9. Regras de identidade e toggle:
   - Sem memória longa quando `memory.long_term.enabled=false`.
   - Em `cloud`, sem identidade autenticada válida não grava memória longa.

10. Retrieval local:
    - Com Qdrant desabilitado, SQLite entrega ranking correto.
    - Com Qdrant habilitado, shortlist semântico + validação final no SQLite.

11. Limites de preload:
    - `PreloadMemoryTool` respeita default de 20 entradas e 1.500 tokens.
    - Excedente não entra no contexto, mas segue persistido.

12. Modo cloud híbrido:
    - Precedência correta entre memória explícita e memória derivada automaticamente.
    - Reconciliação evita duplicação e mantém consistência.

13. Comandos de validação:
    - `make py-setup`
    - `cd apps/acp && .venv/bin/python -m pytest tests -v`
    - `apps/acp/.venv/bin/python apps/acp/scripts/e2e_smoke.py`

## Rollout e Rollback

1. Rollout faseado:
   - Fase 1: habilitar ADK em `local`, validar sessão SQLite persistente, retrieval técnico e `/memory`.
   - Fase 2: habilitar `cloud` com identidade autenticada por sessão no gateway.
   - Fase 3: antes de habilitar extração automática em produção, validar o `memory_extractor` com um golden set manual de 20 conversas reais para calibrar `ACP_MEMORY_MIN_CONFIDENCE` e os thresholds de classificação de conflito (`ACP_MEMORY_SIMILARITY_HIGH` e `ACP_MEMORY_SIMILARITY_MEDIUM`).
   - Critério de saída da validação (valores iniciais calibráveis):
   - taxa máxima de conflito mal classificado <= 10%;
   - taxa máxima de memória indevida registrada <= 5%;
   - taxa mínima de memórias úteis reaproveitadas em conversas posteriores >= 60%.
   - Fase 4: habilitar extração automática em produção somente após cumprir o critério de saída.

2. Rollback:
   - Manter toggle de engine durante transição (`legacy`/`adk`) para rollback rápido sem mudança de contrato ACP/CLI.
   - Reverter `apps/acp` para commit anterior ao ADK se necessário.
   - Sem migração destrutiva de schema; memória antiga permanece legível.

## Assunções e Defaults

1. ADK é obrigatório para runtime/orquestração/memória, não para o núcleo de retrieval técnico.
2. `local` usa SQLite como source of truth para sessão e memória longa por padrão.
3. Qdrant para memória local é opcional e desligado por padrão.
4. `cloud` usa Vertex Session + Memory Bank.
5. Em ambiente internet, memória longa requer identidade autenticada por sessão.
6. `memory_user_id` é derivado por `sha256(tenant + ":" + user.id)` com isolamento adicional por `app_name`/`environment`.
7. `effective_confidence` é derivado em runtime; `confidence` bruto não é sobrescrito.
8. Threshold inicial de extração: `confidence >= 0.7`, calibrável.
9. Thresholds iniciais de similaridade (`0.92` alto, `0.78` médio) são calibráveis e não absolutos.
10. `PreloadMemoryTool` usa defaults seguros de 20 entradas e 1.500 tokens, configuráveis.
