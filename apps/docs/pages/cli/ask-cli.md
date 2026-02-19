# CLI - nova CLI (Python)

Este guia descreve a **nova CLI em Python** (Typer + Rich) integrada ao Toad via ACP.

## Pre-requisitos

- Python 3.12+
- Dependência `agent-client-protocol` (SDK ACP)
- Para `chat`: `batrachian-toad` (requer Python 3.14+)

## Instalação

```bash
cd apps/cli
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Alternativa via Makefile:

```bash
make py:setup
apps/cli/.venv/bin/code-compass ask "onde fica o handler do search_code?" --repo code-compass
```

## Comandos

### `ask`

```bash
code-compass ask "onde fica o handler do search_code?" --repo code-compass
```

O `ask` exibe os chunks do agente quando disponíveis.

### `chat`

```bash
code-compass chat
```

O `chat` tenta abrir o Toad já apontando para o **ACP Agent**. Se o agente estiver
disponível, ele injeta `toad acp <agent-cmd>` automaticamente.
No fluxo padrão (sem `TOAD_COMMAND`), o CLI usa `python -m code_compass_cli.toad_patched`
para habilitar aliases locais `/clear` e `/close`.

## Flags

- `--topk <n>`: número de evidências (default 10)
- `--path-prefix <prefix>`: filtro por prefixo de path
- `--language <lang>`: filtro por linguagem/extensão
- `--repo <name>`: filtra por repositório (para múltiplos repos, use `--repo repo-a,repo-b`)
- `--min-score <n>`: score mínimo para considerar evidências
- `--grounded`: retorna somente trechos do código (sem geração do LLM)
- `--show-meta`: imprime metadados do MCP (modelo/coleção etc.)
- `--show-context`: imprime evidências usadas (path/linhas)
- `--timeout-ms <ms>`: timeout por request
- `--debug`: habilita logs

## Fluxo de execução

- `ask` fala direto com o **ACP Agent** (`apps/acp`), que por sua vez chama o MCP server.
- `chat` abre a TUI do Toad usando `TOAD_COMMAND`/`TOAD_ARGS` ou
  `python -m code_compass_cli.toad_patched` e injeta o agente ACP quando disponível.

## Configuração via env

- `LLM_MODEL` (se definido, sobrescreve o modelo do MCP)
- `MCP_COMMAND`
- `TOAD_PROFILE`
- `TOAD_COMMAND` (binário do toad, opcional)
- `TOAD_ARGS` (args extras para o toad)
- `TOAD_PROJECT_DIR` (path enviado ao `toad acp`; default: diretório atual)
- `ACP_AGENT_CMD` (comando do agente ACP, opcional)
- `ACP_AGENT_ARGS` (args extras do agente ACP)
- `ACP_REPO`, `ACP_PATH_PREFIX`, `ACP_LANGUAGE`, `ACP_TOPK`, `ACP_MIN_SCORE` (override do filtro no agente ACP)
- `ACP_GROUNDED` (força resposta restrita ao contexto)

## Observações

- O comando `chat` exige `batrachian-toad` instalado em Python 3.14+ ou `TOAD_COMMAND` apontando para um binário compatível.
- Dentro do chat, use `/repo <nome>` para trocar para um repo (ex.: `/repo golyzer`) ou `/repo <repo-a,repo-b>` para múltiplos repos.
- Dentro do chat, use `/model <nome>` para trocar o modelo na sessão (use `/model` para ver o atual e `/model reset` para voltar ao default).
- Dentro do chat, use `/grounded <on|off|reset>` para ativar/desativar grounded em runtime.
- Dentro do chat, use `/content-type <code|docs|all|reset>` (ou `/contentType`) para controlar `contentType` em runtime.
- Dentro do chat, use `/config` para visualizar a configuração efetiva da sessão (scope, modelo, filtros e flags).
- Dentro do chat, use `/clear` (alias de `/toad:clear`) para limpar a janela de conversa.
- Dentro do chat, use `/close` (alias de `/toad:session-close`) para fechar a sessão atual.

Guia de manutenção dos slash commands:

- `apps/docs/pages/cli/comandos-slash.md`
