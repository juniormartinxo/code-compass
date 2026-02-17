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

## Variáveis de ambiente

- `MCP_COMMAND`: comando para subir o MCP server (`--transport stdio`)
- `LLM_MODEL`: repassado ao MCP via `env`
- `ACP_REPO`: repo padrão enviado ao `ask_code`

## Notas de operação

- `ask_code` é validado no handshake (`tools/list`).
- Cancelamento interrompe o await do MCP e o loop de chunking.

---

Referência: `apps/acp/src/code_compass_acp/agent.py`.
