# Toad + ACP no Code Compass (chat)

Este guia documenta a integração entre **Toad** e o **ACP Agent** do Code Compass
para uso no comando `code-compass chat`.

## Objetivo

- Abrir o Toad já conectado ao ACP Agent do Code Compass.
- Permitir troca de **repo** e **modelo** dentro da sessão.
- Garantir fallback quando o repo não existe.

## Pré-requisitos

- Toad instalado (binário ou `python -m toad`).
- ACP Agent instalado em `apps/acp/.venv/bin/code-compass-acp` ou via `ACP_AGENT_CMD`.

## Como iniciar o chat

```bash
code-compass chat
```

O CLI tenta abrir o Toad com `acp` e injeta automaticamente o comando do agente.
Se estiver usando `python -m toad`, o comando final fica equivalente a:

```bash
python -m toad acp /caminho/para/code-compass-acp
```

## Variáveis de ambiente relevantes

- `TOAD_COMMAND`: binário do Toad (opcional)
- `TOAD_ARGS`: args extras do Toad
- `ACP_AGENT_CMD`: caminho do agente ACP (opcional)
- `ACP_AGENT_ARGS`: args extras do agente ACP
- `ACP_REPO`: repo default da sessão
- `LLM_MODEL`: modelo default da sessão

## Comandos na sessão (chat)

### Trocar repo

- `/repo` → mostra o repo atual
- `/repo <nome>` → troca o repo da sessão

**Fallback**: se `CODEBASE_ROOT` estiver definido e o repo não existir em
`<CODEBASE_ROOT>/<repo>`, o comando rejeita e mantém o repo atual.

### Trocar modelo

- `/model` → mostra o modelo atual
- `/model <nome>` → troca o modelo da sessão
- `/model reset` → volta ao default (`LLM_MODEL`)

## Troubleshooting rápido

- Se o `/repo` ou `/model` não responder, verifique se o Toad foi aberto via
  `code-compass chat` (o agente precisa ser ACP, não um outro agent do Toad).
- Se houver erro de execução, confira `ACP_AGENT_CMD` e permissões do binário.

