# Antigravity MCP (local, via STDIO)

Este projeto suporta integração local com o cliente Antigravity usando configuração MCP em JSON no formato `mcpServers`.

## Setup rápido

1. Garanta que o repositório está com dependências instaladas (`pnpm install`).
2. Abra o Antigravity.
3. Vá em **MCP Servers**.
4. Clique em **Manage MCP Servers**.
5. Abra **View raw config**.
6. Cole o conteúdo de `apps/docs/assets/antigravity-mcp.json`.
7. Substitua `<REPO_ROOT_AQUI>` pelo caminho absoluto do clone local.
8. Salve a configuração.
9. Reinicie o server MCP no Antigravity se a UI solicitar.

## Template de config

Use `apps/docs/assets/antigravity-mcp.json` como base:

```json
{
  "mcpServers": {
    "code-compass-local": {
      "command": "bash",
      "args": ["-lc", "cd <REPO_ROOT_AQUI> && pnpm --silent mcp:start"]
    }
  }
}
```

Notas:

- O uso de `bash -lc` ajuda a carregar ambiente/PATH (incluindo `pnpm`).
- O uso de `pnpm --silent` evita banner no `stdout`, preservando `stdout` para o protocolo MCP.
- O launcher `bin/dev-mcp` define defaults de `REPO_ROOT`, `QDRANT_URL` e `QDRANT_COLLECTION` sem sobrescrever env já informado pelo usuário.
- Evite depender de `cwd` no config do cliente; o template já faz `cd` explícito para a raiz do projeto.

## Verificação funcional

1. Chame `search_code` com um termo conhecido do repositório.
2. Com um resultado em mãos, chame `open_file` com `path`, `startLine` e `endLine` curtos.
3. Teste segurança com `open_file` em `../../etc/passwd` (esperado: bloqueio com erro de permissão/validação).

## Onde o Antigravity salva o JSON

No ambiente local atual, foi observado o arquivo `~/.gemini/antigravity/mcp_config.json` contendo chave `mcpServers`. Ainda assim, a UI (**Manage MCP Servers → View raw config**) deve ser tratada como fonte de verdade.
