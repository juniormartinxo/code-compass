# Code Compass CLI (Python)

CLI em Python com Typer + Rich integrada ao Toad via ACP.

## Requisitos

- Python 3.14+
- `toad` e `acp` (via dependência `batrachian-toad`)

## Instalação (modo dev)

```bash
cd apps/cli
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Comandos

### `code-compass ask`

Envia uma pergunta ao Code Compass e exibe a resposta no terminal.

```bash
code-compass ask "onde fica o handler do search_code?" --repo code-compass
```

Opções:

- `--repo` — filtro por repositório
- `--path-prefix` — filtro por prefixo de path (ex: `apps/indexer/`)
- `--language` — filtro por linguagem (ex: `python`)
- `--topk` — número de evidências retornadas (default: `10`)
- `--min-score` — score mínimo de relevância (default: `0.6`)
- `--grounded` — restringe a resposta ao contexto recuperado (sem complementar com conhecimento geral)
- `--show-meta` — exibe metadados da chamada ao MCP
- `--show-context` — exibe as evidências utilizadas na resposta
- `--timeout-ms` — timeout total da requisição em milissegundos (default: `120000`)
- `--debug` — ativa modo debug

### `code-compass chat`

Abre a interface TUI do **Toad** já conectada ao **ACP Agent** do Code Compass.

```bash
code-compass chat
```

O Toad é aberto com o agente ACP injetado automaticamente. O CLI aplica aliases de commands (`/clear` e `/close`) e passa o diretório atual como contexto do projeto.

Dentro da sessão é possível usar:

- `/repo <nome>` — troca o repositório em uso (suporta múltiplos com CSV)
- `/model <nome|perfil|reset>` — troca o modelo LLM da sessão
- `/grounded <on|off|reset>` — controla o modo aterrado
- `/knowledge <strict|all|reset>` — controla o modo de conhecimento
- `/content-type <code|docs|all|reset>` — filtra tipo de conteúdo
- `/memory list|forget|clear|enable|disable` — gerencia memória longa
- `/config` — exibe a configuração efetiva da sessão
- `/clear` — limpa o histórico visível (alias de `/toad:clear`)
- `/close` — encerra a sessão (alias de `/toad:session-close`)

Consulte o guia completo em [Toad + ACP no Code Compass](../../apps/docs/pages/cli/toad-chat-acp.md).

## Variáveis de Ambiente

| Variável | Descrição |
| -------- | --------- |
| `MCP_COMMAND` | Comando do MCP server (default: `node apps/mcp-server/dist/main.js --transport stdio`) |
| `LLM_MODEL` | Modelo LLM padrão |
| `TOAD_COMMAND` | Binário do Toad (opcional; se ausente usa o Python do PATH) |
| `TOAD_ARGS` | Args extras passados ao Toad |
| `TOAD_PROJECT_DIR` | Diretório passado como `PATH` ao `toad acp` (default: `cwd`) |
| `ACP_AGENT_CMD` | Caminho do binário do ACP Agent (default: auto-detectado em `apps/acp/.venv/bin/code-compass-acp`) |
| `ACP_AGENT_ARGS` | Args extras passados ao ACP Agent |
| `TOAD_PROFILE` | Perfil do Toad a utilizar |

## Troubleshooting

Consulte [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) para problemas conhecidos e correções manuais.
