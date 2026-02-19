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
- `ACP_MODEL_PROFILES_FILE`: arquivo TOML de perfis para `/model` (default `model-profiles.toml` na raiz, local e não versionado)
- `ACP_REPO`: repo padrão enviado ao `ask_code`
- `ACP_CONTENT_TYPE`: tipo de conteúdo (`code`, `docs`, `all`)
- `ACP_STRICT`: quando `true`, falha em vez de retorno parcial se alguma coleção estiver indisponível

## Slash Commands no Toad

Ao abrir sessão ACP no Toad, o agente anuncia comandos via `available_commands_update`.
Isso permite que o menu fuzzy (`/`) mostre os comandos abaixo:

- `/repo <repo[,repo2,...]>`
- `/config`
- `/model <model|perfil|reset>`
- `/grounded <on|off|reset>`
- `/content-type <code|docs|all|reset>`

Quando o valor de `/model` bate com um perfil do `ACP_MODEL_PROFILES_FILE`, o agente aplica
`model + provider + api_url + api_key` no bridge da sessão e reinicia o subprocesso MCP.
Para forçar lookup por perfil (sem fallback para nome de modelo), use `/model profile:<nome>`.
