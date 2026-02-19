# Agente ACP (Python)

O **Code Compass ACP Agent** expõe a tool `ask_code` via MCP stdio usando o SDK `agent-client-protocol`.

## Visão geral

- Protocolo: **MCP JSON-RPC 2.0** (`initialize → initialized → tools/call`)
- Processo: **persistente por sessão** (handshake assertivo)
- Cancelamento: `asyncio.Event` + `SIGTERM/SIGKILL`
- Streaming: chunk por parágrafos/linhas

## Estrutura

```
apps/acp/
├── pyproject.toml
├── src/code_compass_acp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── agent.py
│   ├── bridge.py
│   └── chunker.py
└── tests/
    └── test_smoke_loopback.py
```

## Como instalar

```bash
pnpm acp:install
```

Ou via Makefile (Python apps):

```bash
make py:setup
```

## Como rodar

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

Se o retorno vier com `stop_reason=refusal`, verifique:

- `MCP_COMMAND` apontando para o MCP server (`apps/mcp-server/dist/main.js`).
- Qdrant ativo (`make up`).
- Indexação realizada (`make index`).

Env vars úteis:

- `ACP_AGENT_CMD`: comando do agente
- `ACP_SMOKE_QUESTION`: pergunta do teste

## Variáveis de ambiente

- `MCP_COMMAND`: comando para subir o MCP server (`--transport stdio`)
- `LLM_MODEL`: repassado ao MCP via `env`
- `ACP_REPO`: repo padrão enviado ao `ask_code`
- `ACP_PATH_PREFIX`, `ACP_LANGUAGE`, `ACP_TOPK`, `ACP_MIN_SCORE`: filtros do `ask_code`
- `ACP_GROUNDED`: força resposta restrita ao contexto
- `ACP_CONTENT_TYPE`: tipo de conteúdo (`code`, `docs`, `all`)
- `ACP_STRICT`: ativa modo estrito no `ask_code`
- `ACP_SHOW_META`, `ACP_SHOW_CONTEXT`: habilitam passthrough de meta/evidences no chat

Comandos de sessão no Toad:

- `/repo` e `/repo <nome|repo-a,repo-b>`: altera escopo de repo(s)
- `/model` e `/model <nome|reset>`: altera modelo da sessão
- `/grounded` e `/grounded <on|off|reset>`: controla grounded em runtime por sessão
- `/content-type` e `/contentType <code|docs|all|reset>`: controla `contentType` em runtime por sessão
- `/config`: imprime a configuração efetiva atual e preview do payload enviado ao MCP

## Notas de operação

- `ask_code` é validado no handshake (`tools/list`).
- Cancelamento interrompe o await do MCP e o loop de chunking.

---

Referência: `apps/acp/src/code_compass_acp/agent.py`.

Para histórico das alterações recentes de slash commands e tutorial de como adicionar
novos comandos, veja:

- `apps/docs/pages/cli/comandos-slash.md`
