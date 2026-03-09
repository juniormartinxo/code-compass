# Operações e Referência Completa do Code Compass

> **Nota:** Estas informações detalhadas foram extraídas do README original para manter a página inicial focada como vitrine. Elas contêm detalhes valiosos sobre a operação, infraestrutura e configuração de clientes do Code Compass.

---

## 📚 Portal de Documentação (Nextra)

O projeto conta com um **portal de documentação interativo** construído com Nextra, acessível em `http://localhost:3000`.

### Comandos Disponíveis

```bash
# Desenvolvimento (localhost:3000)
pnpm docs:dev

# Build de produção
pnpm docs:build

# Preview do build
pnpm docs:start
```

O portal organiza toda a documentação técnica do projeto:
- **Arquitetura** - Visão detalhada
- **ADRs** - Decisões arquiteturais
- **Indexer & RAG** - Pipeline e embeddings
- **CLI** - Interface linha de comando
- **MCP Integration** - Integração de agents

---

## MCP Local Quickstart (Antigravity)

1. `pnpm install`
2. `make up`
3. `make index`
4. `pnpm mcp:start`
5. Abra Antigravity → **MCP Servers** → **Manage MCP Servers** → **View raw config**
6. Cole `apps/docs/assets/antigravity-mcp.json` (substituindo o root do repo)
7. Salve e recarregue o server MCP na UI
8. Teste `search_code` com termo existente
9. Valide segurança com `open_file` em `../../etc/passwd` (deve bloquear)

---

## CLI (ask)

Para usar o chat no terminal (TUI) e o modo one-shot, confira `apps/docs/pages/cli/ask-cli.md`.

Exemplo rápido:

```bash
pnpm ask --repo code-compass
pnpm ask "onde fica o handler do search_code?" --repo code-compass
```

O CLI converte `--repo` para `scope: { type: "repo", repo }` ao chamar o MCP.

---

## Comandos Operacionais (Makefile)

O `Makefile` da raiz já traz os alvos operacionais mínimos para infra + indexer:

```bash
make up                        # sobe qdrant e aguarda readiness
make health                    # valida /readyz
make index                     # alias de indexação full
make index-full                # full em apps/indexer
make index-incremental         # fallback para full (ainda não implementado CLI)
make index-docker              # full via container
make index-all                 # indexa todos os repos de code-base/
make dev                       # sobe apps/mcp-server em dev
make chat-setup                # sobe a infra base para o chat
make chat                      # executa chat com bootstrap automático
make logs                      # logs do qdrant
make down                      # derruba serviços
```

**Observações:**

- Se módulos não existirem (`apps/indexer` ou `apps/mcp-server`), os comandos falham explícito.
- `make docker` instala dependências no container a cada execução.

---

## Flags e env vars essenciais (Indexer)

### Flags de CLI

- `python -m indexer ask --scope-repo <repo>`: escopo de 1 repo.
- `python -m indexer ask --scope-all`: global (requer `ALLOW_GLOBAL_SCOPE=true`).

### Env Vars

- `QDRANT_COLLECTION_BASE`: base para code e docs.
- `CODEBASE_ROOT`: habilitar multi-repo (`<CODEBASE_ROOT>/<repo>`).
- `INDEXER_RUN_MODULE`: módulo rodado pelo docker.

---

## Scanner e Chunking base

O scanner em `apps/indexer/indexer` faz varreduras recursivas. Ignorados por padrão: `.git,node_modules,dist,build,.next,.qdrant_storage,.venv,venv,__pycache__`. Allowlist padrão: `.ts,.tsx,.js,.jsx,.py,.md,.json,.yaml,.yml`.

O Chunking (`python -m indexer chunk`) usa `python_symbol` para arquivos Python validos, `ts_symbol` para `TS / TSX / JS / JSX` validos, `doc_section` para docs por heading, `config_section` para configs por bloco, `sql_statement` para SQL por statement e `line_window` como fallback, com `chunkId` estrutural estavel e `contentHash` separado por conteudo.

No primeiro rollout do schema `v5`, execute **reindexacao completa obrigatoria**. Nao mantenha pontos antigos e novos misturados na mesma collection do Qdrant.

---

## Indexação Multi-Repo (`code-base/`)

O diretório local `code-base/` concentra os clones de repositórios.

```bash
# Indexar todos
./scripts/index-all.sh

# Especificar repositórios
./scripts/index-all.sh repo-frontend repo-backend
```

⚠️ Atenção: Para separar bem no Qdrant, a indexação percorre os repositórios individualmente (loop) e aplica o path do repo no payload do Qdrant.
⚠️ Atenção: Basenames de repo precisam ser únicos; se dois roots diferentes tiverem o mesmo nome, o indexer rejeita a indexação para evitar ambiguidade no escopo público por `repo`.

---

## Integração de Clientes MCP (Detalhado)

O Code Compass suporta transporte **STDIO** (processo local) e **HTTP** (JSON-RPC via `/mcp`).

### A) Claude Desktop
Recomendado usar **STDIO server** (processo local). Adicione o comando `bin/dev-mcp` à configuração do Claude.

### B) Codex (OpenAI Codex CLI/IDE)
`.codex/config.toml`:
```toml
[mcp_servers.code_compass_local]
command = "/ABS/PATH/code-compass/bin/dev-mcp"
args = []
env = { QDRANT_URL = "http://localhost:6333", QDRANT_COLLECTION_BASE = "compass_manutic_nomic_embed" }
```

### C) Cursor
`.cursor/mcp.json` usando as configs de path para o launch local `bin/dev-mcp`.

### D) VS Code & JetBrains
O sistema aceita configs em Json (`.vscode/mcp.json` ou plugins AI Assistant no IntelliJ) da mesma forma apontando para o binário via STDIO ou HTTP. 

### Rodando em HTTP Remoto
```bash
pnpm -C apps/mcp-server build
pnpm -C apps/mcp-server start:http
```
Endpoint: `POST http://<host>:3001/mcp` (JSON-RPC 2.0).

---

## Observabilidade
- **Logs estruturados** no MCP Server NestJS.
- **Métricas Chave**: latência P95 do `search_code`, taxa de resposta com evidência de código, e tracking de `no hits` para mapear problemas do indexador.
