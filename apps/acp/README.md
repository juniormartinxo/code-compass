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

## Variáveis de ambiente

- `MCP_COMMAND`: comando do MCP server (`--transport stdio`)
- `LLM_MODEL`: repassado ao MCP
- `ACP_REPO`: repo padrão enviado ao `ask_code`
