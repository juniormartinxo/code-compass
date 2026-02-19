# Toad + ACP no Code Compass (chat)

Este guia documenta a integração entre **Toad** e o **ACP Agent** do Code Compass
para uso no comando `code-compass chat`.

## Objetivo

- Abrir o Toad já conectado ao ACP Agent do Code Compass.
- Permitir troca de **repo**, **modelo** e **grounded** dentro da sessão.
- Garantir fallback quando o repo não existe.

## Pré-requisitos

- Toad instalado (binário ou `python -m toad`).
- ACP Agent instalado em `apps/acp/.venv/bin/code-compass-acp` ou via `ACP_AGENT_CMD`.

## Como iniciar o chat

```bash
code-compass chat
```

O CLI tenta abrir o Toad com `acp` e injeta automaticamente o comando do agente.
Por padrão, o `code-compass chat` usa um launcher do próprio CLI para aplicar aliases
de comandos (`/clear` e `/close`), então o comando final fica equivalente a:

```bash
python -m code_compass_cli.toad_patched acp /caminho/para/code-compass-acp
```

Além do comando do agente, o CLI passa o diretório atual como `PATH` para o
`toad acp`, evitando erro ao fechar sessão e voltar para a Store.

Se `TOAD_COMMAND` estiver definido, o CLI respeita esse binário/comando externo e
os aliases dependem do comportamento desse comando.

## Variáveis de ambiente relevantes

- `TOAD_COMMAND`: binário do Toad (opcional)
- `TOAD_ARGS`: args extras do Toad
- `TOAD_PROJECT_DIR`: diretório usado como `PATH` no `toad acp` (default: `cwd`)
- `ACP_AGENT_CMD`: caminho do agente ACP (opcional)
- `ACP_AGENT_ARGS`: args extras do agente ACP
- `ACP_REPO`: repo default da sessão
- `LLM_MODEL`: modelo default da sessão

## Comandos na sessão (chat)

### Trocar repo

- `/repo` → mostra o repo atual
- `/repo <nome>` → troca para um único repo na sessão
- `/repo <repo-a,repo-b>` → troca para múltiplos repos (CSV, sem aspas)

**Fallback**: se `CODEBASE_ROOT` estiver definido e o repo não existir em
`<CODEBASE_ROOT>/<repo>`, o comando rejeita e mantém o repo atual.

### Trocar modelo

- `/model` → mostra o modelo atual
- `/model <nome>` → troca o modelo da sessão
- `/model reset` → volta ao default (`LLM_MODEL`)

### Controlar grounded

- `/grounded` → mostra o status atual (`on`/`off`) e a fonte (`env` ou `sessão`)
- `/grounded on` → ativa grounded para a sessão atual
- `/grounded off` → desativa grounded para a sessão atual
- `/grounded reset` → remove override da sessão e volta a usar `ACP_GROUNDED`

### Controlar contentType

- `/content-type` ou `/contentType` → mostra o `contentType` atual da sessão
- `/content-type code` → força `contentType=code` na sessão
- `/content-type docs` → força `contentType=docs` na sessão
- `/content-type all` → força `contentType=all` na sessão
- `/content-type reset` → remove override e volta ao valor de `ACP_CONTENT_TYPE`

### Ver configuração atual

- `/config` → mostra a configuração efetiva da sessão, incluindo:
  - `scope` (repo único ou múltiplos repos)
  - `llmModel`
  - `grounded` (ativo, fonte env/sessão e override)
  - `contentType` (ativo, fonte env/sessão e override)
  - filtros (`pathPrefix`, `language`, `topK`, `minScore`, `contentType`)
  - flags (`grounded`, `strict`, `showMeta`, `showContext`)
  - preview do payload enviado ao `ask_code`

### Aliases de comandos do Toad

- `/clear` → alias de `/toad:clear`
- `/close` → alias de `/toad:session-close`

Os comandos originais do Toad continuam funcionando normalmente.

## Troubleshooting rápido

- Se o `/repo`, `/model`, `/grounded` ou `/config` não responder, verifique se o Toad foi aberto via
  `code-compass chat` (o agente precisa ser ACP, não um outro agent do Toad).
- Se houver erro de execução, confira `ACP_AGENT_CMD` e permissões do binário.

## Referência de manutenção

Para histórico das alterações e guia de extensão de novos comandos, veja:

- [Comandos Slash: Histórico e Extensão](./comandos-slash)
