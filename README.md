# Code Compass 🧭

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white) ![Node.js](https://img.shields.io/badge/Node.js-LTS-339933?logo=node.js&logoColor=white) ![NestJS](https://img.shields.io/badge/NestJS-MCP%20Server-E0234E?logo=nestjs&logoColor=white) ![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20DB-DC244C?logo=qdrant&logoColor=white) ![MCP](https://img.shields.io/badge/MCP-Tools%20Gateway-6E56CF)

**RAG + MCP para navegar e perguntar sobre codebases com rastreabilidade.**

O Code Compass indexa repositórios (código e documentação), gera embeddings, armazena no **Qdrant** e expõe ferramentas via **MCP (Model Context Protocol)** para clientes/agents (CLI, IDE, etc.). O foco aqui é **engenharia de plataforma**: ingestão, chunking, busca, segurança de leitura de arquivo e integração com clientes.

---

## Por que isso existe
Em codebase grande, “achar a verdade” vira gargalo: onboarding lento, debugging caro, refactors arriscados.
O Code Compass reduz tempo de ciclo com:
- **Busca semântica** (com metadados de arquivo/linhas)
- **Respostas com citações** (arquivo + trecho)
- **Abrir arquivo com range de linhas** com regras de segurança
- Pipeline modular para evoluir chunking, ranking e avaliação

---

## Arquitetura (alto nível)
**Pipeline**
1. **Scan** do repo → coleta arquivos elegíveis
2. **Chunk** → fatia conteúdo em trechos com metadados (`path`, `startLine`, `endLine`, hashes)
3. **Embed** → gera vetores
4. **Upsert** → grava no Qdrant (`payload` rico)

**Serving**
- **MCP Server (NestJS)** expõe tools:
  - `search_code` (busca)
  - `ask_code` (Q&A sobre o contexto recuperado)
  - `open_file` (leitura segura com range)

> Design thinking: separar **ingestão** de **serving** pra escalar/depurar por camadas. Veja os detalhes em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Stack
- **Node.js + NestJS** (MCP server)
- **Python** (indexer/chunker/embeddings)
- **Qdrant** (vector database)
- Docker Compose para infraestrutura local

---

## Quickstart (demo em repo público)

![Demo GIF](docs/demo.gif)

### 1) Subir Qdrant
```bash
make up
# ou: docker compose -f infra/docker-compose.yml up -d
```

### 2) Preparar um repo para indexar

Estrutura sugerida:

```text
code-base/
  nest/
  nextjs/
```

Clone exemplos públicos:

```bash
mkdir -p code-base
git clone https://github.com/nestjs/nest.git code-base/nest
git clone https://github.com/vercel/next.js.git code-base/nextjs
```

### 3) Configurar env (exemplo)

Crie seu `.env.local` baseado em `.env.example`.

### 4) Indexar

```bash
make index
```

### 5) Rodar o MCP Server

```bash
make dev
```

---

## Segurança e governança (o básico bem feito)

* `open_file` **não permite escape** do root configurado
* Bloqueio de `..`, caminhos absolutos e traversal
* Estrutura preparada para **scope** (por repo / multi-repo) com defaults seguros

> Segurança aqui não é “feature”, é pré-requisito.

---

## O que este projeto já entrega (MVP)

* Scan + chunk + upsert no Qdrant
* Busca por similaridade com metadados
* MCP server com tools principais
* `open_file` com range e guardrails

## Próximas evoluções (roadmap)

* Indexação incremental (delta por hash/mtime)
* Split físico `code` vs `docs` + merge por **RRF**
* Avaliação automática (golden set + regressão)
* Híbrida BM25 + dense (opcional)
* Conectores (GitHub/GitLab/Bitbucket)

---

## Como eu uso isso

* Localmente para acelerar leitura de codebase
* Como base para integrar em clientes MCP/ACP (CLI/IDE)

> Para o guia detalhado de infraestrutura, CLI, configs completas, plugins IDE (Cursor, Claude, VSCode, etc) e operações de chunking e indexação, consulte o diretório secundário em [`docs/OPERATIONS.md`](docs/OPERATIONS.md) e o portal Nextra nativo do repositório.

---

## Contribuição

PRs são bem-vindos. Se for mexer em pipeline, mantenha:

* logs legíveis
* metadados consistentes (`repo`, `path`, `startLine/endLine`)
* mudanças com validação mínima (smoke test)

---

## Licença

**Apache-2.0**
