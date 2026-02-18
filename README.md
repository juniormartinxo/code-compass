# Code Compass

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white) ![Node.js](https://img.shields.io/badge/Node.js-LTS-339933?logo=node.js&logoColor=white) ![NestJS](https://img.shields.io/badge/NestJS-MCP%20Server-E0234E?logo=nestjs&logoColor=white) ![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20DB-DC244C?logo=qdrant&logoColor=white) ![MCP](https://img.shields.io/badge/MCP-Tools%20Gateway-6E56CF)

**Code Compass** é um **servidor MCP + pipeline RAG** para a base de código de qualquer empresa.

Ele indexa repositórios (código + docs), gera embeddings e armazena tudo em um **Vector DB (Qdrant)**, expondo **tools via MCP** para agentes como **Codex, Gemini e Claude** consultarem a codebase com **evidência** (trecho + path + linha + score).

> Stack definida: **Node/NestJS (MCP Server) + Python (Indexer/ML Worker) + Qdrant (Vector DB)**

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
   - coleções separadas para `code` e `docs` (stem via `QDRANT_COLLECTION_BASE`, com sufixos `__code`/`__docs`) + payload rico (repo, commit, path, linguagem, linhas, etc.)
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

### 1) Configure `.env.local`
Crie `.env.local` a partir de `.env.example` (inclui `LLM_MODEL` para o comando `ask`).

> O `Makefile` prioriza `.env.local` quando o arquivo existe.

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
6. Cole `apps/docs/assets/antigravity-mcp.json` (substitua `<REPO_ROOT_AQUI>`)
7. Salve e recarregue o server MCP na UI, se solicitado
8. Teste `search_code` com termo existente no repositório
9. Teste `open_file` usando `path/startLine/endLine` de um hit
10. Valide segurança com `open_file` em `../../etc/passwd` (deve bloquear)

Referências rápidas: `apps/docs/pages/mcp-antigravity.md` e `apps/docs/assets/antigravity-mcp.json`.

---

## CLI (ask)

Para usar o chat no terminal (TUI) e o modo one-shot, veja `apps/docs/pages/cli/ask-cli.md`.

Exemplo rapido:

```bash
pnpm ask --repo code-compass
pnpm ask "onde fica o handler do search_code?" --repo code-compass
```

No fluxo atual, o CLI converte `--repo` para `scope: { type: "repo", repo }` ao chamar o MCP.

---

## 📚 Portal de Documentação

O projeto agora conta com um **portal de documentação interativo** construído com [Nextra](https://nextra.site), acessível em `http://localhost:3000`.

### Features do Portal

- ✅ **Busca Full-Text** nativa com FlexSearch
- ✅ **Dark Mode** habilitado por padrão
- ✅ **Navegação automática** entre páginas
- ✅ **Syntax highlighting** para código
- ✅ **Mobile-responsive**
- ✅ **Performance otimizado** com geração estática (SSG)

### Comandos Disponíveis

```bash
# Desenvolvimento (localhost:3000)
pnpm docs:dev

# Build de produção
pnpm docs:build

# Preview do build
pnpm docs:start
```

### Conteúdo Documentado

O portal organiza toda a documentação técnica do projeto:

- **Arquitetura** - Visão detalhada da arquitetura do sistema
- **ADRs** - 6 decisões arquiteturais documentadas
- **Indexer & RAG** - Pipeline de indexação e embeddings
- **CLI** - Interface de linha de comando
- **MCP Integration** - Integração com Model Context Protocol

Para mais detalhes, consulte o [`apps/docs/README.md`](apps/docs/README.md).

---

## Comandos (Makefile)

O `Makefile` da raiz já traz os alvos operacionais mínimos para infra + indexer:

```bash
make up                        # sobe qdrant e aguarda readiness
make health                    # valida /readyz
make index                     # alias de indexação full
make index-full                # full em apps/indexer
make index-incremental         # fallback para full (incremental ainda não implementado no CLI)
make index-docker              # full via container (profile indexer)
make index-docker-incremental  # fallback para full via container
make index-all                 # indexa todos os repos de code-base/
make dev                       # sobe apps/mcp-server em dev
make logs                      # logs do qdrant
make down                      # derruba serviços
```

Observações importantes do estado atual deste repositório:

- Se `apps/indexer` ainda não existir, `make index*` falha com erro explícito de pré-requisito.
- Se `apps/mcp-server` ainda não existir, `make dev` falha com erro explícito de pré-requisito.
- O `make up` usa `.env.local` (quando existir) ou `.env` para portas/imagem/path de storage.
- `make index-docker*` exige Docker e instala dependências do indexer dentro do container a cada execução.
- `make index-incremental` e `make index-docker-incremental` fazem fallback para indexação full atualmente.

## Flags e env vars essenciais (estado atual)

### Flags de CLI

- `pnpm ask --repo <repo>`: escopo de um repositório para `ask_code` (via ACP, convertido em `scope`).
- `python -m indexer ask --scope-repo <repo>`: escopo explícito de 1 repo.
- `python -m indexer ask --scope-repos "repo-a,repo-b"`: escopo explícito multi-repo.
- `python -m indexer ask --scope-all`: escopo global (requer `ALLOW_GLOBAL_SCOPE=true`).

### Env vars operacionais

- `QDRANT_COLLECTION_BASE`: stem compartilhado entre indexador e MCP (coleções finais: `__code` e `__docs`).
- `CODEBASE_ROOT`: habilita roteamento multi-repo no MCP (`<CODEBASE_ROOT>/<repo>`).
- `ALLOW_GLOBAL_SCOPE=true`: habilita `scope: { type: "all" }` em `search_code` e `ask_code`.
- `INDEXER_RUN_MODULE=indexer`: módulo Python usado pelo `Makefile`/docker para indexação.
- `MCP_COMMAND`: comando customizado para `python -m indexer ask` chamar o MCP server.
- `CODE_COMPASS_TIMEOUT_MS`: timeout (ms) para `pnpm ask` (CLI/TUI).

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

## Indexação Multi-Repo (`code-base/`)

O diretório `code-base/` é o ponto central para indexar **múltiplos repositórios** de uma só vez. Cada subdiretório dentro dele é tratado como um repositório independente pelo pipeline de indexação.

### Estrutura

```
code-base/
├── .gitkeep          # garante que o diretório exista no git
├── repo-frontend/    # git clone do projeto frontend
├── repo-backend/     # git clone do projeto backend
└── shared-lib/       # git clone de uma lib compartilhada
```

> ⚠️ O conteúdo de `code-base/` é ignorado pelo git (veja `.gitignore`). Apenas o `.gitkeep` é versionado.

### Preparação

Clone os repositórios que deseja indexar dentro de `code-base/`:

```bash
git clone git@gitlab.empresa.com:team/repo-frontend.git code-base/repo-frontend
git clone git@gitlab.empresa.com:team/repo-backend.git  code-base/repo-backend
```

### Script `scripts/index-all.sh`

Script bash que automatiza a indexação de todos os repositórios dentro de `code-base/`.

**O que faz:**

1. Carrega as variáveis de ambiente de `.env.local`
2. Ativa o virtualenv do indexer (`apps/indexer/.venv`)
3. Itera sobre cada subdiretório de `code-base/`
4. Define `REPO_ROOT` e executa `python -m indexer index` para cada repo
5. Exibe um resumo final com contagem de sucessos e falhas

**Atenção (comportamento atual do indexador):**

- O comando `index` processa **um único** `repo_root` por execução.
- O campo `payload.repo` é preenchido com o nome do diretório informado em `--repo-root`/`REPO_ROOT`.
- Se você rodar com `REPO_ROOT=/.../code-base`, todos os pontos serão gravados com `payload.repo="code-base"`.
- Nesse cenário, o filtro por `repo` no MCP não consegue separar corretamente `repo-frontend`, `repo-backend`, etc.
- Para multi-repo real, indexe cada subdiretório individualmente (ex.: `scripts/index-all.sh`).

**Uso:**

```bash
# Indexar todos os repos dentro de code-base/
./scripts/index-all.sh

# Indexar apenas repos específicos (por nome do diretório)
./scripts/index-all.sh repo-frontend shared-lib

# Ou via Makefile (garante Qdrant + venv antes)
make index-all
```

**Pré-requisitos:**

- Qdrant rodando (`make up`)
- Ollama rodando com o modelo de embedding configurado
- Virtualenv do indexer criado (`make setup-indexer`)
- Pelo menos um repositório clonado em `code-base/`

**Exit code:** retorna `0` se todos os repos foram indexados com sucesso, `1` se algum falhou (útil para CI/CD).

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

## Configuração (`.env.local` / `.env`)

Prioridade de carregamento no fluxo atual:

1. variáveis já exportadas no shell
2. `.env.local`
3. `.env`

Exemplo (base em `.env.example`):

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
# Qdrant
# -----------------------------
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION_BASE=compass__manutic_nomic_embed
QDRANT_DISTANCE=COSINE
QDRANT_UPSERT_BATCH=64

# -----------------------------
# Repos / ingestão
# -----------------------------
REPO_ROOT=/abs/path/para/repositorio
REPO_ALLOWLIST=src,packages,apps,docs
REPO_BLOCKLIST=node_modules,dist,build,.next,.git,coverage
SCAN_IGNORE_DIRS=.git,node_modules,dist,build,.next,.qdrant_storage,coverage,.venv,venv,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache
SCAN_ALLOW_EXTS=.ts,.tsx,.js,.jsx,.py,.md,.json,.yaml,.yml

# -----------------------------
# Indexer (apps/indexer)
# -----------------------------
INDEXER_DIR=apps/indexer
INDEXER_PYTHON=python3
INDEXER_RUN_MODULE=indexer
INDEXER_DOCKER_PROFILE=indexer
INDEXER_DOCKER_IMAGE=python:3.11-slim
QDRANT_URL_DOCKER=http://qdrant:6333
REPO_ROOT_DOCKER=/workspace

# -----------------------------
# Embeddings (Ollama)
# -----------------------------
EMBEDDING_PROVIDER_CODE=ollama
EMBEDDING_PROVIDER_DOCS=ollama
OLLAMA_URL=http://localhost:11434
EMBEDDING_MODEL_CODE=manutic/nomic-embed-code
EMBEDDING_MODEL_DOCS=bge-m3
EMBEDDING_BATCH_SIZE=16
EMBEDDING_MAX_RETRIES=5
EMBEDDING_BACKOFF_BASE_MS=500
EMBEDDING_TIMEOUT_SECONDS=120
LLM_MODEL=gpt-oss:latest

# -----------------------------
# Chunking
# -----------------------------
CHUNK_LINES=120
CHUNK_OVERLAP_LINES=20

# -----------------------------
# MCP Server
# -----------------------------
MCP_SERVER_NAME=code-compass
MCP_SERVER_PORT=3333
CODEBASE_ROOT=/abs/path/para/code-base
ALLOW_GLOBAL_SCOPE=false

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

* `compass__manutic_nomic_embed` (exemplo)

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

### `ask_code`

Executa o fluxo RAG completo (embedding + busca + contexto + LLM) no servidor MCP.

> V1 (opcional): `find_symbol`, `git_log`, `git_blame`, rerank.

---

## Como conectar no Claude/Gemini/Codex via MCP

> **Importante:** clientes MCP podem suportar diferentes transportes. O Code Compass suporta **STDIO** (processo local) e **HTTP** (endpoint JSON-RPC em `/mcp`). Alguns clientes também usam **HTTP/SSE**; sempre siga a doc do cliente.

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

### Rodando em HTTP (server remoto)

Use transporte HTTP quando quiser hospedar o MCP em um servidor:

```bash
pnpm -C apps/mcp-server build
pnpm -C apps/mcp-server start:http
```

Configurações úteis:

- `MCP_HTTP_HOST` (default: `0.0.0.0`)
- `MCP_HTTP_PORT` (default: `3001`)
- `MCP_SERVER_MODE=http` (alternativa ao `--transport http`)

Endpoint MCP: `POST http://<host>:<port>/mcp` (JSON-RPC 2.0).


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
* Indexer Python: full (incremental em evolução)
* MCP Server NestJS: `search_code`, `open_file`, `ask_code`
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
