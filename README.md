# Code Compass

**Code Compass** é um **servidor MCP + pipeline RAG** para a base de código da empresa.  
Ele indexa repositórios (código + docs), gera embeddings e armazena tudo em um **Vector DB (Qdrant)**, expondo **tools via MCP** para agentes como **Codex, Gemini e Claude** consultarem a codebase com **evidência** (trecho + path + linha + score).

> Stack definida (Opção A): **Node/NestJS (MCP Server) + Python (Indexer/ML Worker) + Qdrant (Vector DB)**

---

## Por que essa stack

- **Node/NestJS**: gateway MCP robusto, integração fácil, validação, audit trail, DX bom.
- **Python Worker**: onde a “IA de verdade” vive (chunking, embeddings, rerank, avaliação).
- **Qdrant**: roda **local/offline** no MVP e escala depois como serviço compartilhado sem replatform.

---

## Arquitetura (alto nível)

1. **Indexer (Python)**
   - varre repositórios e docs
   - faz chunking (AST quando possível; fallback heurístico)
   - gera embeddings
   - faz `upsert` no Qdrant com payload rico (metadados)

2. **Vector Store (Qdrant)**
   - coleção `code_chunks` com vetores + payload (repo, commit, path, linguagem, linhas, etc.)
   - filtros por payload (repo/pathPrefix/lang/branch/commit)
   - busca semântica + (opcional) híbrida

3. **MCP Server (Node/NestJS)**
   - expõe tools para clientes MCP
   - faz validação/allowlist de paths
   - orquestra chamadas ao Qdrant e ao filesystem/git
   - retorna resultados com evidência (path/linhas)

---

## Requisitos

- Docker + Docker Compose (para Qdrant local)
- Node.js (LTS recomendado)
- Python 3.11+ (recomendado)
- Acesso ao(s) repositório(s) a indexar

---

## Quickstart (plug and play)

### 1) Configure `.env`
Crie `.env` a partir de `.env.example`.

### 2) Suba o Qdrant
```bash
make up
```

Endpoint local do Qdrant: `http://localhost:6333`.

Healthcheck rápido:

```bash
curl -s http://localhost:6333/readyz
```

### 3) Rode indexação (primeira carga)

```bash
make index
```

### 4) Suba o MCP Server

```bash
make dev
```

## MCP Local Quickstart (Antigravity)

1. `pnpm install`
2. `make up`
3. `make index`
4. `pnpm mcp:start`
5. Abra Antigravity → **MCP Servers** → **Manage MCP Servers** → **View raw config**
6. Cole `docs/antigravity-mcp.json` (substitua `<REPO_ROOT_AQUI>`)
7. Salve e recarregue o server MCP na UI, se solicitado
8. Teste `search_code` com termo existente no repositório
9. Teste `open_file` usando `path/startLine/endLine` de um hit
10. Valide segurança com `open_file` em `../../etc/passwd` (deve bloquear)

Referências rápidas: `docs/mcp-antigravity.md` e `docs/antigravity-mcp.json`.

---

## CLI (ask)

Para usar o chat no terminal (TUI) e o modo one-shot, veja `docs/cli/ask-cli.md`.

Exemplo rapido:

```bash
pnpm ask
pnpm ask "onde fica o handler do search_code?"
```

---

## Comandos (Makefile)

O `Makefile` da raiz já traz os alvos operacionais mínimos para infra + indexer:

```bash
make up                        # sobe qdrant e aguarda readiness
make health                    # valida /readyz
make index                     # alias de indexação full
make index-full                # full em apps/indexer
make index-incremental         # incremental em apps/indexer
make index-docker              # full via container (profile indexer)
make index-docker-incremental  # incremental via container
make dev                       # sobe apps/mcp-server em dev
make logs                      # logs do qdrant
make down                      # derruba serviços
```

Observações importantes do estado atual deste repositório:

- Se `apps/indexer` ainda não existir, `make index*` falha com erro explícito de pré-requisito.
- Se `apps/mcp-server` ainda não existir, `make dev` falha com erro explícito de pré-requisito.
- O `make up` usa `.env` (ou defaults seguros) para portas/imagem/path de storage.
- `make index-docker*` exige Docker e instala dependências do indexer dentro do container a cada execução.

## Scanner base do Indexer

O scanner recursivo do indexador fica em `apps/indexer/indexer` e retorna JSON com:

- `files`: arquivos elegíveis (relativos ao `repo_root`, em formato posix)
- `stats`: métricas do scan (`total_files_seen`, `files_kept`, `elapsed_ms`, etc.)

Execução mínima:

```bash
cd apps/indexer
python -m indexer scan
```

Configuração por ambiente:

- `REPO_ROOT`: raiz do scan. Padrão: `..` (um nível acima de `apps/indexer`).
- `SCAN_ALLOW_EXTS`: CSV opcional para sobrescrever extensões permitidas.
- `SCAN_IGNORE_DIRS`: CSV opcional para adicionar diretórios ignorados.

Ignorados por padrão:

`.git,node_modules,dist,build,.next,.qdrant_storage,coverage,.venv,venv,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache`

Allowlist padrão de extensões:

`.ts,.tsx,.js,.jsx,.py,.md,.json,.yaml,.yml`

Exemplo com env inline:

```bash
cd apps/indexer
REPO_ROOT=/home/juniormartinxo/code-compass \
SCAN_ALLOW_EXTS=.py,.md,.ts,.tsx \
SCAN_IGNORE_DIRS=node_modules,dist,build,.git \
python -m indexer scan --max-files 50
```

## Chunking MVP por arquivo

O comando `chunk` gera chunks determinísticos por linhas com overlap, `chunkId` estável e `contentHash` no payload.

Execução mínima:

```bash
cd apps/indexer
python -m indexer chunk --file path/to/file
```

Variáveis de ambiente:

- `REPO_ROOT`: raiz para path canônico relativo (padrão: `..`).
- `CHUNK_LINES`: tamanho máximo de cada chunk em linhas (padrão: `120`).
- `CHUNK_OVERLAP_LINES`: overlap entre chunks consecutivos (padrão: `20`).

Flags relevantes:

- `--chunk-lines`: override de `CHUNK_LINES`.
- `--overlap-lines`: override de `CHUNK_OVERLAP_LINES`.
- `--repo-root`: override de `REPO_ROOT`.
- `--as-posix` / `--no-as-posix`: controla separador do path canônico; o padrão é `--as-posix` para estabilidade cross-OS e menor atrito em filtros/payload no Qdrant.

Exemplo:

```bash
cd apps/indexer
python -m indexer chunk \
  --file apps/indexer/indexer/chunk.py \
  --repo-root .. \
  --chunk-lines 120 \
  --overlap-lines 20 \
  --as-posix
```

Formato de saída (resumo):

- `path`: path canônico relativo ao `repoRoot` (quando possível).
- `pathIsRelative`: `true` quando o arquivo está sob `REPO_ROOT`.
- `chunks[]`:
  - `chunkId`: hash estável de `path:startLine:endLine:contentHash`.
  - `contentHash`: SHA-256 do conteúdo completo do arquivo (debug/dedupe/incremental).
  - `startLine`/`endLine`: range 1-based inclusivo.
  - `language`: inferido por extensão.
  - `content`: conteúdo textual do chunk.

## Debug search (CLI)

Após indexar, use o comando `search` do indexer para debug rápido no Qdrant:

```bash
cd apps/indexer
python -m indexer search "minha query" --topk 10
```

Com filtro por prefixo de path no payload:

```bash
cd apps/indexer
python -m indexer search "minha query" --topk 10 --path_prefix src/
```

Saída humana esperada por resultado:

```text
[1] score=0.7821  src/foo/bar.ts:120-168
    snippet: "..."
```

---

## Infra (Qdrant local)

`infra/docker-compose.yml`:

```yaml
name: ${COMPOSE_PROJECT_NAME:-code-compass}

services:
  qdrant:
    container_name: code-compass-qdrant
    image: ${QDRANT_IMAGE:-qdrant/qdrant:latest}
    restart: unless-stopped
    ports:
      - "${QDRANT_HTTP_PORT:-6333}:6333"   # HTTP
      - "${QDRANT_GRPC_PORT:-6334}:6334"   # gRPC
    volumes:
      - "${QDRANT_STORAGE_PATH:-../.qdrant_storage}:/qdrant/storage"
    healthcheck:
      test: ["CMD-SHELL", "bash -c 'exec 3<>/dev/tcp/127.0.0.1/6333'"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
```

Verificar:

```bash
curl -s http://localhost:6333/
curl -s http://localhost:6333/readyz
```

---

## Configuração (.env)

Exemplo (`.env.example`):

```env
# -----------------------------
# Docker Compose
# -----------------------------
COMPOSE_PROJECT_NAME=code-compass

# -----------------------------
# Qdrant (infra local)
# -----------------------------
QDRANT_IMAGE=qdrant/qdrant:latest
QDRANT_HTTP_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_STORAGE_PATH=../.qdrant_storage

# -----------------------------
# Repos / ingestão
# -----------------------------
REPO_ROOT=/abs/path/para/repositorio
REPO_ALLOWLIST=src,packages,apps,docs
REPO_BLOCKLIST=node_modules,dist,build,.next,.git,coverage
SCAN_IGNORE_DIRS=.git,node_modules,dist,build,.next,.qdrant_storage,coverage,.venv,venv,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache
SCAN_ALLOW_EXTS=.ts,.tsx,.js,.jsx,.py,.md,.json,.yaml,.yml

# -----------------------------
# Qdrant
# -----------------------------
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=code_chunks
QDRANT_DISTANCE=Cosine

# -----------------------------
# Indexer (apps/indexer)
# -----------------------------
INDEXER_DIR=apps/indexer
INDEXER_PYTHON=python3
INDEXER_RUN_MODULE=code_compass.index
INDEXER_DOCKER_PROFILE=indexer
INDEXER_DOCKER_IMAGE=python:3.11-slim
QDRANT_URL_DOCKER=http://qdrant:6333
REPO_ROOT_DOCKER=/workspace

# -----------------------------
# Embeddings
# -----------------------------
EMBEDDINGS_PROVIDER=openai          # openai | local
EMBEDDINGS_MODEL=text-embedding-3-large
OPENAI_API_KEY=YOUR_KEY

# -----------------------------
# Chunking
# -----------------------------
CHUNK_MAX_TOKENS=800
CHUNK_OVERLAP_TOKENS=120

# -----------------------------
# MCP Server
# -----------------------------
MCP_SERVER_NAME=code-compass
MCP_SERVER_PORT=3333

# -----------------------------
# Segurança / Governança
# -----------------------------
READ_ONLY=true
AUDIT_LOG_ENABLED=true
PATH_TRAVERSAL_GUARD=true
```

---

## Modelo de dados no Qdrant

### Collection

* `code_chunks`

### Point

* `id`: string única (ex.: `<repo>:<commit>:<path>:<chunkHash>`)
* `vector`: embedding
* `payload`:

  * `repo`, `branch`, `commit`
  * `path`, `language`
  * `startLine`, `endLine`
  * `symbols` (opcional)
  * `text` (trecho do chunk) **ou** `textRef` (se preferir guardar chunk fora)

---

## Tools MCP (MVP)

### `search_code`

Busca semântica no Qdrant com filtros por payload.

### `open_file`

Abre um trecho do arquivo (fonte de verdade) por range de linhas.

### `list_tree`

Lista árvore de arquivos dentro do allowlist.

> V1 (opcional): `find_symbol`, `git_log`, `git_blame`, rerank.

---

## Como conectar no Claude/Gemini/Codex via MCP

> **Importante:** clientes MCP podem suportar diferentes transportes. Alguns preferem **STDIO** (server local executado como processo), outros suportam **HTTP/SSE**. Sempre siga a doc do cliente.

### A) Claude (Claude Desktop)

A forma mais comum é registrar um **servidor local** no Claude Desktop (o cliente lança o processo do server). A doc oficial de “connect local servers” mostra o fluxo geral com Claude Desktop.

**Padrão recomendado para Claude Desktop:**

* rodar o MCP server como **STDIO server** (processo local)
* apontar o comando para iniciar o Code Compass

> Observação: o formato exato de configuração varia por versão do Claude Desktop e método (extensão/instalação local). Consulte a página oficial de setup local. ([Claude Help Center][5])

**Dica prática:**

* Tenha um script `apps/mcp-server/start-stdio.sh` que sobe o NestJS em modo MCP-stdio (sem logs em stdout “sujo”).
* E configure o Claude pra chamar esse script.

---

### B) Codex (OpenAI Codex CLI / IDE)

Codex lê a config em `~/.codex/config.toml` (ou em `.codex/config.toml` por projeto).

**Exemplo de configuração (STDIO) — `.codex/config.toml`:**

```toml
[mcp_servers.code_compass]
command = "node"
args = ["apps/mcp-server/dist/main.js"]
env = { "MCP_SERVER_MODE" = "stdio" }
```

> Ajuste `command/args` conforme seu build. A doc do Codex detalha como registrar MCP servers no `config.toml`.

**Workflow sugerido:**

1. `make up`
2. `make index`
3. build do server (`npm run build`)
4. configurar `config.toml`
5. usar Codex apontando para o projeto

---

### C) Gemini (duas rotas comuns)

#### C1) Gemini CLI

O Gemini CLI tem suporte a MCP servers e documenta como configurar.

Aqui também é comum usar **STDIO** para servidor local.

> Recomendação: se sua intenção é “Gemini no terminal”, Gemini CLI é o caminho mais previsível.

#### C2) Gemini no Android Studio (Agent mode)

O Android Studio tem fluxo próprio para **adicionar MCP server** ao agente do Gemini.
Útil se o time está muito preso em Android Studio/JetBrains e quer toolchain “na IDE”.

---

## Segurança e Governança (não negociável)

* **Read-only** por padrão
* **Allowlist** de diretórios/repositórios
* Proteção contra `../` (path traversal)
* **Audit trail** de tool calls (quem, quando, query, filtros, repos tocados)
* (Opcional) redator/detector de segredos antes de indexar

---

## Observabilidade (recomendado)

* Logs estruturados no MCP Server (NestJS)
* Métricas sugeridas:

  * latência P95 do `search_code`
  * taxa de respostas com evidência (path+linha)
  * top queries / “no hits” (gaps de indexação)

---

## Roadmap

### MVP

* Qdrant local via Docker
* Indexer Python: full + incremental
* MCP Server NestJS: `search_code`, `open_file`, `list_tree`
* Retorno com evidência (path/linha) sempre

### V1

* Busca híbrida (sparse + dense) e/ou rerank top-N
* Filtros avançados (módulo, dono, tags)
* `git_log`/`git_blame`

### V2

* Grafo de símbolos (def/ref)
* Multi-tenant por time/projeto
* Avaliação automática (golden queries)
* Policy packs (compliance)

---

## Licença

Uso interno (definir conforme política da empresa).
