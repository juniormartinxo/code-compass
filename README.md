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
docker compose -f infra/docker-compose.yml up -d
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

---

## Comandos (Makefile)

> Você pode rodar tudo com `make`. Se preferir, execute os comandos manualmente nos diretórios.

Crie um `Makefile` na raiz do projeto com:

```makefile
SHELL := /bin/bash

.PHONY: help up down logs dev index index-full index-incremental clean

help:
	@echo "Targets:"
	@echo "  make up               -> sobe Qdrant (docker compose)"
	@echo "  make down             -> derruba Qdrant"
	@echo "  make logs             -> logs do Qdrant"
	@echo "  make index            -> indexação full (primeira carga)"
	@echo "  make index-incremental-> indexação incremental"
	@echo "  make dev              -> sobe MCP Server (NestJS)"
	@echo "  make clean            -> limpa storage local do Qdrant (CUIDADO)"

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f qdrant

index: index-full

index-full:
	cd apps/indexer && \
	python -m venv .venv >/dev/null 2>&1 || true && \
	source .venv/bin/activate && \
	pip install -r requirements.txt && \
	python -m code_compass.index full

index-incremental:
	cd apps/indexer && \
	source .venv/bin/activate && \
	python -m code_compass.index incremental

dev:
	cd apps/mcp-server && \
	npm install && \
	npm run dev

clean:
	rm -rf .qdrant_storage
```

---

## Infra (Qdrant local)

`infra/docker-compose.yml`:

```yaml
name: code-compass

services:
  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    ports:
      - "6333:6333"   # HTTP
      - "6334:6334"   # gRPC
    volumes:
      - ../.qdrant_storage:/qdrant/storage
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
# Repos / ingestão
# -----------------------------
REPO_ROOT=/abs/path/para/monorepo
REPO_ALLOWLIST=src,packages,apps,docs
REPO_BLOCKLIST=node_modules,dist,build,.next,.git,coverage

# -----------------------------
# Qdrant
# -----------------------------
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=code_chunks
QDRANT_DISTANCE=Cosine
QDRANT_VECTOR_SIZE=3072

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
