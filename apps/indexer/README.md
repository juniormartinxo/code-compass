# Indexer

Pipeline de indexação de código para o Code Compass.

## Visão Geral

O Indexer é responsável por:

1. **Scan** - Escanear repositórios de código
2. **Chunk** - Dividir arquivos em chunks semânticos (por símbolo, seção ou janela de linhas)
3. **Embed** - Gerar embeddings via provider HTTP configurável
4. **Upsert** - Armazenar vetores no Qdrant com payload rico
5. **Search** - Busca semântica nos chunks indexados
6. **Ask** - Perguntas em linguagem natural via RAG

## Pré-requisitos

- Python 3.12+
- Provider de embedding configurado (default: **Ollama** local com `manutic/nomic-embed-code` e `bge-m3`)
- **Qdrant** rodando localmente

### Instalar modelos no Ollama (default)

```bash
ollama pull manutic/nomic-embed-code
ollama pull bge-m3
```

### Iniciar Qdrant

Na raiz do projeto:

```bash
make up
```

## Setup

### 1. Criar ambiente virtual

```bash
cd apps/indexer
python3 -m venv .venv
source .venv/bin/activate
pip install httpx qdrant-client
```

### 2. Configurar variáveis de ambiente

```bash
# Embeddings
export EMBEDDING_PROVIDER_CODE=ollama
export EMBEDDING_PROVIDER_DOCS=ollama
export EMBEDDING_PROVIDER_CODE_API_URL=http://localhost:11434
export EMBEDDING_PROVIDER_DOCS_API_URL=http://localhost:11434
export EMBEDDING_PROVIDER_CODE_API_KEY=
export EMBEDDING_PROVIDER_DOCS_API_KEY=
export EMBEDDING_MODEL_CODE=manutic/nomic-embed-code
export EMBEDDING_MODEL_DOCS=bge-m3
export EMBEDDING_BATCH_SIZE=16

# Qdrant
export QDRANT_URL=http://localhost:6333
export QDRANT_COLLECTION_BASE=compass_manutic_nomic_embed
export QDRANT_DISTANCE=COSINE
export QDRANT_UPSERT_BATCH=64

# Repositório
export REPO_ROOT=/path/to/your/repository
```

Ou copie e edite o `.env.example` na raiz do projeto (inclui `LLM_MODEL` para o comando `ask`).

## Chunking Semântico

O indexer utiliza **estratégias de chunking adaptadas por tipo de arquivo**, respeitando a estrutura sintática e semântica de cada linguagem. O campo `chunk_strategy` no payload do Qdrant indica qual estratégia foi utilizada.

### Estratégias disponíveis

| Estratégia | Arquivos | Descrição |
| ---------- | -------- | --------- |
| `python_symbol` | `.py` | Extrai funções, métodos e classes via AST nativo do Python |
| `ts_symbol` | `.ts`, `.tsx`, `.js`, `.jsx` | Extrai funções, componentes React, hooks e classes via parser TS |
| `doc_section` | `.md`, `.mdx`, `.rst` etc. | Divide por heading/subheading |
| `config_section` | `.env`, `.toml`, `.yaml`, `.json`, `.ini` | Divide por seção/bloco de configuração |
| `sql_statement` | `.sql` | Divide por statement SQL ou bloco coerente |
| `line_window` | Qualquer arquivo | Fallback por janela de linhas (usado quando parse falha ou a extensão não tem parser dedicado) |

**Fallback automático**: se o parse sintático falhar para Python ou TS, o chunker recai silenciosamente para `line_window`, registrando um warning no resultado.

### Classificação de conteúdo (`chunk_content_type`)

Além da estratégia de chunking, cada ponto recebe uma classificação semântica interna (`chunk_content_type`):

| Valor | Descrição |
| ----- | --------- |
| `code_symbol` | Bloco de código com símbolo identificado (função, classe, componente) |
| `code_context` | Bloco de código genérico sem símbolo identificado |
| `doc_section` | Seção de documentação (`.md`, `.rst`, etc.) |
| `config_block` | Bloco de arquivo de configuração |
| `sql_block` | Bloco SQL |
| `test_case` | Arquivo ou bloco de teste (detectado por path/nome) |

O campo `content_type` (de coleção) continua sendo `code` ou `docs` para roteamento entre collections do Qdrant.

### Metadados semânticos por linguagem

Quando o parser extrai um símbolo (Python ou TypeScript), os seguintes campos ficam disponíveis no payload:

- `symbol_name` — nome simples do símbolo (ex: `parse_chunk`)
- `qualified_symbol_name` — nome qualificado com contexto (ex: `ChunkParser.parse_chunk`)
- `symbol_type` — tipo: `function`, `method`, `class`, `component`, `hook`, `arrow_function`, etc.
- `parent_symbol` — símbolo pai (para métodos dentro de uma classe)
- `signature` — assinatura completa do símbolo (parâmetros e tipo de retorno quando disponível)
- `imports` — importações relevantes do arquivo (lista)
- `exports` — exportações do arquivo (lista)
- `callers` — símbolos que chamam este (grafo de 1 salto aproximado, lista)
- `callees` — símbolos chamados por este (lista)
- `summary_text` — resumo gerado com path, language, range e nome de símbolo
- `context_text` — contexto expandido do chunk

## Comandos

### Scan

Escaneia o repositório e lista arquivos para indexação:

```bash
python -m indexer scan --repo-root /path/to/repo
```

Opções:

- `--repo-root` - Caminho do repositório (default: env `REPO_ROOT`)
- `--allow-exts` - Extensões permitidas (.ts,.py,.md)
- `--ignore-dirs` - Diretórios para ignorar
- `--max-files` - Limite máximo de arquivos

### Chunk

Gera chunks de um arquivo específico:

```bash
python -m indexer chunk --file /path/to/file.py
```

Opções:

- `--file` - Arquivo para chunkar (obrigatório)
- `--chunk-lines` - Linhas por chunk no fallback `line_window` (default: 120)
- `--overlap-lines` - Overlap entre chunks no fallback `line_window` (default: 20)
- `--repo-root` - Raiz do repositório
- `--as-posix` / `--no-as-posix` - Usar paths POSIX

### Init

Inicializa as collections de `code` e `docs` no Qdrant (**idempotente**):

```bash
python -m indexer init
```

Este comando:

1. Conecta ao provider de embedding e **descobre o vector_size** de `code` e `docs` automaticamente
2. Resolve/gera os nomes das collections de `code` e `docs`
3. Cria/valida collections no Qdrant
4. Garante índice payload `content_type` (`keyword`)

**Saída:**

```json
{
  "embedding": {
    "code": {
      "provider": "ollama",
      "api_url": "http://localhost:11434",
      "model": "manutic/nomic-embed-code",
      "vector_size": 3584
    },
    "docs": {
      "provider": "ollama",
      "api_url": "http://localhost:11434",
      "model": "bge-m3",
      "vector_size": 3584
    }
  },
  "collections": {
    "code": {
      "name": "compass_manutic_nomic_embed__code",
      "action": "created"
    },
    "docs": {
      "name": "compass_manutic_nomic_embed__docs",
      "action": "created"
    }
  },
  "distance": "COSINE",
  "qdrant_url": "http://localhost:6333",
  "payload_index": {
    "content_type": {
      "schema": "keyword",
      "status": {
        "code": true,
        "docs": true
      }
    }
  }
}
```

Opções:

- `--api-url-code` - URL da API de embedding para `code`
- `--api-url-docs` - URL da API de embedding para `docs`
- `--api-key-code` - API key para provider de `code` (opcional no Ollama)
- `--api-key-docs` - API key para provider de `docs` (opcional no Ollama)
- `--provider-code` - Provider de embedding para `code`
- `--provider-docs` - Provider de embedding para `docs`
- `--model-code` - Modelo de embedding para `code`
- `--model-docs` - Modelo de embedding para `docs`
- `--qdrant-url` - URL do Qdrant

### Index

Executa o pipeline completo de indexação:

```bash
python -m indexer index --repo-root /path/to/repo
```

Este comando:

1. **Scan** - Escaneia o repositório
2. **Chunk** - Divide cada arquivo em chunks usando a estratégia semântica adequada
3. **Embed** - Gera embeddings em batches via provider por tipo de conteúdo
4. **Upsert** - Armazena vetores no Qdrant com IDs estáveis e payload rico

**IDs estáveis**: o `chunk_id` representa a identidade estrutural do chunk. Em `line_window`, ele é ancorado em `path:start:end:language`; em chunking por símbolo, passa a ser ancorado em metadados estruturais como `qualifiedSymbolName`. O `content_hash` representa a versão textual atual do conteúdo do chunk.

**Migração de schema**: a introdução de `chunk_schema_version=v5` exige **reindexação completa obrigatória** no rollout desta fase. Não tente misturar pontos antigos e novos na mesma collection; descarte os pontos antigos ou recrie a collection antes do rebuild.

**Saída:**

```json
{
  "status": "success",
  "repo_root": "/path/to/repo",
  "collections": {
    "code": "compass_manutic_nomic_embed__code",
    "docs": "compass_manutic_nomic_embed__docs"
  },
  "files_scanned": 42,
  "files_indexed": 42,
  "file_coverage": 1.0,
  "chunks_total": 156,
  "chunks_by_type": {
    "code": 120,
    "docs": 36
  },
  "chunk_errors": 0,
  "embeddings_generated": 156,
  "embeddings_generated_by_type": {
    "code": 120,
    "docs": 36
  },
  "points_upserted": 156,
  "upsert_by_type": {
    "code": { "points_upserted": 120, "batches": 2 },
    "docs": { "points_upserted": 36, "batches": 1 }
  },
  "embedding": {
    "code": {
      "provider": "ollama",
      "model": "manutic/nomic-embed-code",
      "vector_size": 3584
    },
    "docs": {
      "provider": "ollama",
      "model": "bge-m3",
      "vector_size": 3584
    }
  },
  "elapsed_ms": 12345,
  "elapsed_sec": 12.35
}
```

Opções:

- `--repo-root` - Caminho do repositório
- `--allow-exts` - Extensões permitidas
- `--ignore-dirs` - Diretórios para ignorar
- `--max-files` - Limite máximo de arquivos
- `--chunk-lines` - Linhas por chunk no fallback `line_window` (default: 120)
- `--overlap-lines` - Overlap entre chunks no fallback `line_window` (default: 20)

### Search

Busca semântica na collection indexada:

```bash
python -m indexer search "query de busca"
```

**Exemplo:**

```bash
python -m indexer search "como fazer chunking de arquivos"
```

**Saída:**

```text
🔍 Query: "como fazer chunking de arquivos"
📊 5 resultado(s):

  1. [0.7879] apps/docs/pages/indexer/commands/chunk.md
     📍 Linhas: 1-21 | Extensão: .md
  ...
```

Opções:

- `query` - Texto da busca (obrigatório)
- `-k`, `--top-k`, `--topk` - Número de resultados (default: 10)
- `--ext` - Filtrar por extensão (ex: `.py`)
- `--language` - Filtrar por linguagem (ex: `python`)
- `--content-type` - Filtrar por tipo (`code`, `docs`, `all`)
- `--json` - Output em JSON

### Ask (RAG)

Perguntas em linguagem natural usando RAG:

```bash
python -m indexer ask "sua pergunta aqui" --scope-repo code-compass
```

**Exemplo:**

```bash
python -m indexer ask "qual banco de dados vetorial é usado neste projeto?" --scope-repo code-compass --show-context
```

**Saída:**

```text
💬 **Pergunta:** qual banco de dados vetorial é usado neste projeto?

🤖 **Resposta:**
O banco de dados vetorial usado neste projeto é o **Qdrant**.

📚 **Fontes consultadas:**
  1. apps/docs/pages/ADRs/ADR-02.md (linhas 1-120) - score: 0.8495
  ...

⏱️  Tempo: 15.32s | Modelo: gpt-oss:latest
```

Opções:

- `question` - Pergunta em linguagem natural (obrigatório)
- `-k`, `--top-k` - Número de chunks de contexto (default: 5)
- `--model` - Modelo LLM para resposta (default: `gpt-oss:latest`)
- `--ext` - Filtrar contexto por extensão
- `--show-context` - Mostrar fontes consultadas
- `--json` - Output em JSON
- `--scope-repo` - Escopo explícito para um repo
- `--scope-repos` - Escopo explícito para vários repos (CSV)
- `--scope-all` - Escopo global (depende de `ALLOW_GLOBAL_SCOPE=true` no MCP)
- `--content-type` - Tipo de conteúdo no MCP (`code`, `docs`, `all`)
- `--strict` - Falha se alguma coleção estiver indisponível (sem retorno parcial)

Importante:

- Para `ask`, é obrigatório informar um escopo via `--scope-*`.

## Variáveis de Ambiente

### Embeddings

| Variável | Default | Descrição |
| ---------- | --------- | ----------- |
| `EMBEDDING_PROVIDER_CODE` | `ollama` | Provider de embeddings para `code` |
| `EMBEDDING_PROVIDER_DOCS` | `ollama` | Provider de embeddings para `docs` |
| `EMBEDDING_PROVIDER_CODE_API_URL` | `http://localhost:11434` | URL da API para embeddings `code` |
| `EMBEDDING_PROVIDER_DOCS_API_URL` | `http://localhost:11434` | URL da API para embeddings `docs` |
| `EMBEDDING_PROVIDER_CODE_API_KEY` | vazio | API key do provider para `code` (opcional no `ollama`) |
| `EMBEDDING_PROVIDER_DOCS_API_KEY` | vazio | API key do provider para `docs` (opcional no `ollama`) |
| `EMBEDDING_MODEL_CODE` | `manutic/nomic-embed-code` | Modelo de embedding para `code` |
| `EMBEDDING_MODEL_DOCS` | `bge-m3` | Modelo de embedding para `docs` |
| `EMBEDDING_BATCH_SIZE` | `16` | Textos por batch de embedding |
| `EMBEDDING_MAX_RETRIES` | `5` | Máximo de tentativas em caso de erro |
| `EMBEDDING_BACKOFF_BASE_MS` | `500` | Base para backoff exponencial (ms) |
| `EMBEDDING_TIMEOUT_SECONDS` | `120` | Timeout de request |

### Qdrant

| Variável | Default | Descrição |
| ---------- | --------- | ----------- |
| `QDRANT_URL` | `http://localhost:6333` | URL do Qdrant |
| `QDRANT_API_KEY` | - | API key (opcional) |
| `QDRANT_COLLECTION_BASE` | `compass_manutic_nomic_embed` | Stem para nome das collections |
| `QDRANT_DISTANCE` | `COSINE` | Métrica de distância (COSINE, EUCLID, DOT) |
| `QDRANT_UPSERT_BATCH` | `64` | Pontos por batch de upsert |
| `INDEX_MIN_FILE_COVERAGE` | `0.95` | Cobertura mínima de arquivos no `index` |
| `SEARCH_SNIPPET_MAX_CHARS` | `300` | Limite de caracteres no snippet de `search` |
| `DOC_EXTENSIONS` | `.md,.mdx,.rst,.adoc,.txt` | Extensões classificadas como `docs` |
| `DOC_PATH_HINTS` | `/docs/,/documentation/,/adr,...` | Pistas de path para classificar como `docs` |
| `EXCLUDED_CONTEXT_PATH_PARTS` | `/.venv/,/venv/,...` | Paths excluídos do contexto em `ask` |
| `CONTENT_TYPES` | `code,docs` | Tipos de conteúdo usados no split de collections |

Observação sobre autenticação no Qdrant:

- Se `QDRANT_API_KEY` estiver vazia (ex.: `QDRANT_API_KEY=`), o cliente é inicializado sem API key.
- Em ambiente local com `QDRANT_URL=http://...`, isso evita o warning `Api key is used with an insecure connection`.

### Scan/Chunk

| Variável | Default | Descrição |
| ---------- | --------- | ----------- |
| `REPO_ROOT` | `..` | Raiz do repositório |
| `SCAN_IGNORE_DIRS` | `.git,node_modules,dist,build,.next,.qdrant_storage,coverage,.venv,venv,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache` | Diretórios a ignorar |
| `SCAN_ALLOW_EXTS` | `.ts,.tsx,.py,.md,...` | Extensões permitidas |
| `SCAN_IGNORE_PATTERNS` | vazio | Padrões glob para ignorar arquivos específicos (ex.: `docs/**`, `**/*.test.ts`). Prioridade: CLI (`--ignore-patterns`) > Env > Default. |
| `CHUNK_LINES` | `120` | Linhas por chunk no fallback `line_window` |
| `CHUNK_OVERLAP_LINES` | `20` | Overlap entre chunks no fallback `line_window` |

### LLM (comando ask)

| Variável | Default | Descrição |
| ---------- | --------- | ----------- |
| `LLM_MODEL` | `gpt-oss:latest` | Modelo LLM padrão do `ask` (prioridade: `--model` > `LLM_MODEL` > default interno) |
| `MCP_COMMAND` | `node apps/mcp-server/dist/main.js --transport stdio` | Comando usado pelo `ask` para chamar o MCP |

## Payload do Ponto

Cada ponto indexado no Qdrant contém:

```json
{
  "repo": "my-project",
  "path": "src/main.py",
  "chunk_index": 0,
  "chunk_id": "a1b2c3d4...",
  "content_hash": "abc123...",
  "chunk_schema_version": "v5",
  "chunk_strategy": "python_symbol",
  "ext": ".py",
  "mtime": 1707456789.123,
  "size_bytes": 1234,
  "text_len": 500,
  "start_line": 1,
  "end_line": 45,
  "language": "python",
  "content_type": "code",
  "chunk_content_type": "code_symbol",
  "source": "repo",
  "repo_root": "/home/user/project",
  "text": "def parse_chunk(...): ...",
  "symbol_name": "parse_chunk",
  "qualified_symbol_name": "ChunkParser.parse_chunk",
  "symbol_type": "method",
  "parent_symbol": "ChunkParser",
  "signature": "def parse_chunk(self, text: str) -> list[ChunkDocument]:",
  "imports": ["from .models import ChunkDocument"],
  "exports": [],
  "callers": ["ChunkParser.index_file"],
  "callees": ["tokenize", "split_by_symbol"],
  "summary_text": "python · src/main.py · lines 1-45 · method ChunkParser.parse_chunk",
  "context_text": "..."
}
```

Observação importante:

- O valor de `repo` vem do nome do `REPO_ROOT` usado na execução.
- Em ambiente multi-repo (`code-base/`), não use `REPO_ROOT` apontando para a pasta agregadora.
- Indexe cada subdiretório (`code-base/<repo>`) separadamente para preservar o filtro por `repo` no MCP.
- O basename de cada repo indexado precisa ser único dentro da mesma base; se houver dois roots diferentes com o mesmo nome, o indexer rejeita a operação para evitar ambiguidade.

## Nome Automático de Collection

O stem base da collection é o valor de `QDRANT_COLLECTION_BASE`.

```text
{QDRANT_COLLECTION_BASE}
```

Exemplo:

```text
compass_manutic_nomic_embed
```

Os nomes finais usados no Qdrant são:

- `{QDRANT_COLLECTION_BASE}__code`
- `{QDRANT_COLLECTION_BASE}__docs`

## Idempotência e Migração de Schema

- `init`: Pode ser executado múltiplas vezes. Se a collection já existir com o mesmo vector_size, apenas valida.
- `index`: IDs são determinísticos. Reindexar o mesmo conteúdo não duplica pontos.
- **Reindexação obrigatória ao mudar schema**: ao fazer upgrade de `chunk_schema_version`, os pontos antigos devem ser descartados ou a collection recriada. Não tente mesclar pontos de versões diferentes.

## Testes

```bash
cd apps/indexer
source .venv/bin/activate
pip install pytest
python -m pytest tests/ -v
```

## Troubleshooting

### "Erro no embedder: Falha ao obter vector size"

- Verifique se a API do provider está acessível (ex.: `curl http://localhost:11434/api/tags` no Ollama)
- Verifique se o modelo está disponível no provider configurado

### "Collection X tem vector size Y, mas embedding é size Z"

O modelo de embedding mudou. Opções:

1. Use outro `QDRANT_COLLECTION_BASE`
2. Delete a collection existente via API do Qdrant

### "Erro no Qdrant: conexão recusada"

- Verifique se o Qdrant está rodando: `curl http://localhost:6333`

### "Sem evidencia suficiente" no `ask`

- Confirme que `QDRANT_COLLECTION_BASE` no indexer e no MCP server é o mesmo valor.
- Verifique se o `repo` informado no comando bate com `payload.repo` indexado.
- Reindexe para atualizar payloads antigos sem `repo`.

### "chunk_strategy sempre retorna line_window"

- Verifique se a extensão do arquivo está entre as suportadas pelos parsers semânticos (`.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.md`, `.sql`, `.toml`, `.yaml`, `.json`, etc.).
- Verifique o campo `warnings` na saída do comando `chunk` para mensagens de fallback.
