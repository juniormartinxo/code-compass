# Code Compass ACP Agent

Agente ACP (Python) que expõe `ask_code` do Code Compass via MCP stdio.

## Instalação

```bash
pnpm acp:install
```

## Execução

```bash
apps/acp/.venv/bin/code-compass-acp
```

## Smoke test (E2E)

Pré-requisitos: MCP server buildado + Qdrant + indexação.

```bash
pnpm mcp:build
make up
make index

apps/acp/.venv/bin/python apps/acp/scripts/e2e_smoke.py
```

Env vars úteis:

- `ACP_AGENT_CMD`: comando do agente (default `apps/acp/.venv/bin/code-compass-acp`)
- `ACP_SMOKE_QUESTION`: pergunta do teste

## Variáveis de ambiente

- `MCP_COMMAND`: comando do MCP server (`--transport stdio`)
- `LLM_MODEL`: repassado ao MCP
- `AGENT_RUNTIME_MODE`: `local|cloud` (default `local`)
- `ACP_ENGINE`: `legacy|adk` (default `legacy`; mantém caminho MCP atual)
- `ACP_MODEL_PROFILES_FILE`: arquivo TOML de perfis para `/model` (default `model-profiles.toml` na raiz, local e não versionado)
- `ACP_REPO`: repo padrão enviado ao `ask_code`
- `ACP_CONTENT_TYPE`: tipo de conteúdo (`code`, `docs`, `all`)
- `ACP_KNOWLEDGE_MODE`: modo de conhecimento (`strict`, `all`, default `strict`)
- `ACP_MEMORY_MAX_TURNS`: quantidade máxima de turnos da sessão enviados como contexto (default `8`)
- `ACP_MEMORY_MAX_CHARS`: limite de caracteres do contexto de sessão enviado ao MCP (default `4000`)
- `ACP_APP_NAME`: namespace lógico da memória (default `code-compass`)
- `ACP_ENVIRONMENT`: namespace de ambiente para memória/sessão (default `local`)
- `ACP_SESSION_BACKEND`: `sqlite|memory` (default `sqlite` em `local`)
- `ACP_SESSION_DB_PATH`: caminho SQLite de sessão (default = `ACP_MEMORY_DB_PATH`)
- `ACP_MEMORY_DB_PATH`: caminho SQLite de memória longa (`apps/acp/.data/memory.sqlite3`)
- `ACP_MEMORY_SCOPE_MODE`: `session|user` (default `user`)
- `ACP_MEMORY_LONG_TERM_ENABLED`: toggle default de memória longa (default `true`)
- `ACP_MEMORY_QDRANT_INDEX_ENABLED`: habilita shortlist semântico opcional (default `false`)
- `ACP_MEMORY_SIMILARITY_MODE`: `lexical|semantic` (default `lexical`)
- `ACP_MEMORY_SIMILARITY_HIGH`, `ACP_MEMORY_SIMILARITY_MEDIUM`: thresholds de conflito/reinforcement
- `ACP_PRELOAD_MEMORY_MAX_ENTRIES`: limite de entradas de preload (default `20`)
- `ACP_PRELOAD_MEMORY_MAX_TOKENS`: limite de tokens do preload (default `1500`)
- `ACP_STRICT`: quando `true`, falha em vez de retorno parcial se alguma coleção estiver indisponível

## Slash Commands no Toad

Ao abrir sessão ACP no Toad, o agente anuncia comandos via `available_commands_update`.
Isso permite que o menu fuzzy (`/`) mostre os comandos abaixo:

- `/repo <repo[,repo2,...]>`
- `/config`
- `/model <model|perfil|reset>`
- `/grounded <on|off|reset>`
- `/knowledge <strict|all|reset>`
- `/content-type <code|docs|all|reset>`
- `/memory list|forget <termo>|clear|enable|disable|why <id|termo>|confirm <id>`

`/grounded on`: mantém resposta estritamente ancorada no contexto recuperado.
`/grounded off` + `/knowledge strict` (default): responde apenas com RAG/código; sem evidência retorna mensagem de ausência de contexto.
`/grounded off` + `/knowledge all`: permite complementar com conhecimento geral do modelo.

O ACP mantém memória por sessão: perguntas/respostas anteriores entram no campo `conversationContext` do `ask_code`,
respeitando `ACP_MEMORY_MAX_TURNS` e `ACP_MEMORY_MAX_CHARS`.

Além do contexto imediato, o ACP agora mantém memória longa em SQLite com isolamento por
`app_name + environment + tenant + user`, controlável por `set_config_option` (`user.id`,
`user.tenant`, `memory.scope.mode`, `memory.long_term.enabled`, `app.name`) e por comandos `/memory`.

Quando o valor de `/model` bate com um perfil do `ACP_MODEL_PROFILES_FILE`, o agente aplica
`model + provider + api_url + api_key` no bridge da sessão e reinicia o subprocesso MCP.
Para forçar lookup por perfil (sem fallback para nome de modelo), use `/model profile:<nome>`.
