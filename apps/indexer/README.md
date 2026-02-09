# Indexer

Pipeline de indexação de código para o Code Compass.

## Visão Geral

O Indexer é responsável por:
1. **Scan** - Escanear repositórios de código
2. **Chunk** - Dividir arquivos em chunks semânticos
3. **Embed** - Gerar embeddings via Ollama
4. **Upsert** - Armazenar vetores no Qdrant
5. **Search** - Busca semântica nos chunks indexados
6. **Ask** - Perguntas em linguagem natural via RAG

## Pré-requisitos

- Python 3.12+
- **Ollama** rodando localmente com o modelo `manutic/nomic-embed-code`
- **Qdrant** rodando localmente

### Instalar Modelo no Ollama

```bash
ollama pull manutic/nomic-embed-code
```

### Iniciar Qdrant

Via Docker:
```bash
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

Ou via docker-compose na raiz do projeto:
```bash
docker-compose up -d qdrant
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
# Ollama
export EMBEDDING_PROVIDER=ollama
export OLLAMA_URL=http://localhost:11434
export EMBEDDING_MODEL=manutic/nomic-embed-code
export EMBEDDING_BATCH_SIZE=16

# Qdrant
export QDRANT_URL=http://localhost:6333
export QDRANT_COLLECTION_BASE=compass
export QDRANT_DISTANCE=COSINE
export QDRANT_UPSERT_BATCH=64

# Repositório
export REPO_ROOT=/path/to/your/repository
```

Ou copie e edite o `.env.example` na raiz do projeto.

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
- `--chunk-lines` - Linhas por chunk (default: 120)
- `--overlap-lines` - Overlap entre chunks (default: 20)
- `--repo-root` - Raiz do repositório
- `--as-posix` / `--no-as-posix` - Usar paths POSIX

### Init

Inicializa a collection no Qdrant (**idempotente**):

```bash
python -m indexer init
```

Este comando:
1. Conecta ao Ollama e **descobre o vector_size** automaticamente
2. Resolve/gera o nome da collection
3. Cria a collection no Qdrant (se não existir)
4. Valida se collection existente tem size compatível

**Saída:**
```json
{
  "provider": "ollama",
  "ollama_url": "http://localhost:11434",
  "model": "manutic/nomic-embed-code",
  "vector_size": 3584,
  "collection_name": "compass__3584__manutic_nomic_embed_code",
  "distance": "COSINE",
  "qdrant_url": "http://localhost:6333",
  "action": "created"
}
```

Opções:
- `--ollama-url` - URL do Ollama
- `--model` - Modelo de embedding
- `--qdrant-url` - URL do Qdrant
- `--collection` - Nome explícito da collection

### Index

Executa o pipeline completo de indexação:

```bash
python -m indexer index --repo-root /path/to/repo
```

Este comando:
1. **Scan** - Escaneia o repositório
2. **Chunk** - Divide cada arquivo em chunks
3. **Embed** - Gera embeddings em batches via Ollama
4. **Upsert** - Armazena vetores no Qdrant com IDs estáveis

**IDs estáveis**: Reindexar o mesmo arquivo/chunk não duplica pontos. Se o texto não mudou, o ID permanece o mesmo e o upsert é um no-op/overwrite.

**Saída:**
```json
{
  "status": "success",
  "repo_root": "/path/to/repo",
  "collection_name": "compass__3584__manutic_nomic_embed_code",
  "files_scanned": 42,
  "chunks_total": 156,
  "chunk_errors": 0,
  "embeddings_generated": 156,
  "points_upserted": 156,
  "upsert_batches": 3,
  "vector_size": 3584,
  "model": "manutic/nomic-embed-code",
  "elapsed_ms": 12345,
  "elapsed_sec": 12.35
}
```

Opções:
- `--repo-root` - Caminho do repositório
- `--allow-exts` - Extensões permitidas
- `--ignore-dirs` - Diretórios para ignorar
- `--max-files` - Limite máximo de arquivos
- `--chunk-lines` - Linhas por chunk (default: 120)
- `--overlap-lines` - Overlap entre chunks (default: 20)

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
```
🔍 Query: "como fazer chunking de arquivos"
📊 5 resultado(s):

  1. [0.7879] docs/indexer/commands/chunk.md
     📍 Linhas: 1-21 | Extensão: .md
  ...
```

Opções:
- `query` - Texto da busca (obrigatório)
- `-k`, `--top-k` - Número de resultados (default: 5)
- `--ext` - Filtrar por extensão (ex: `.py`)
- `--language` - Filtrar por linguagem (ex: `python`)
- `--json` - Output em JSON

### Ask (RAG)

Perguntas em linguagem natural usando RAG:

```bash
python -m indexer ask "sua pergunta aqui"
```

**Exemplo:**
```bash
python -m indexer ask "qual banco de dados vetorial é usado neste projeto?" --show-context
```

**Saída:**
```
💬 **Pergunta:** qual banco de dados vetorial é usado neste projeto?

🤖 **Resposta:**
O banco de dados vetorial usado neste projeto é o **Qdrant**.

📚 **Fontes consultadas:**
  1. docs/ADRs/ADR-02.md (linhas 1-120) - score: 0.8495
  ...

⏱️  Tempo: 15.32s | Modelo: llama3.2
```

Opções:
- `question` - Pergunta em linguagem natural (obrigatório)
- `-k`, `--top-k` - Número de chunks de contexto (default: 5)
- `--model` - Modelo LLM para resposta (default: `llama3.2`)
- `--ext` - Filtrar contexto por extensão
- `--show-context` - Mostrar fontes consultadas
- `--json` - Output em JSON

## Variáveis de Ambiente

### Ollama (Embeddings)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `EMBEDDING_PROVIDER` | `ollama` | Provider de embeddings |
| `OLLAMA_URL` | `http://localhost:11434` | URL do Ollama |
| `EMBEDDING_MODEL` | `manutic/nomic-embed-code` | Modelo de embedding |
| `EMBEDDING_BATCH_SIZE` | `16` | Textos por batch de embedding |
| `EMBEDDING_MAX_RETRIES` | `5` | Máximo de tentativas em caso de erro |
| `EMBEDDING_BACKOFF_BASE_MS` | `500` | Base para backoff exponencial (ms) |
| `EMBEDDING_TIMEOUT_SECONDS` | `120` | Timeout de request |

### Qdrant

| Variável | Default | Descrição |
|----------|---------|-----------|
| `QDRANT_URL` | `http://localhost:6333` | URL do Qdrant |
| `QDRANT_API_KEY` | - | API key (opcional) |
| `QDRANT_COLLECTION_BASE` | `compass` | Base para nome da collection |
| `QDRANT_COLLECTION` | - | Nome explícito (se não definido, auto-gera) |
| `QDRANT_DISTANCE` | `COSINE` | Métrica de distância (COSINE, EUCLID, DOT) |
| `QDRANT_UPSERT_BATCH` | `64` | Pontos por batch de upsert |

### Scan/Chunk

| Variável | Default | Descrição |
|----------|---------|-----------|
| `REPO_ROOT` | `..` | Raiz do repositório |
| `SCAN_IGNORE_DIRS` | `.git,node_modules,dist,build,.next,.qdrant_storage,coverage,.venv,venv,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache` | Diretórios a ignorar |
| `SCAN_ALLOW_EXTS` | `.ts,.tsx,.py,.md,...` | Extensões permitidas |
| `CHUNK_LINES` | `120` | Linhas por chunk |
| `CHUNK_OVERLAP_LINES` | `20` | Overlap entre chunks |

### LLM (comando ask)

| Variável | Default | Descrição |
|----------|---------|-----------|
| `LLM_MODEL` | `llama3.2` | Modelo LLM para gerar respostas no `ask` |

## Payload do Ponto

Cada ponto indexado no Qdrant contém:

```json
{
  "path": "src/main.py",
  "chunk_index": 0,
  "content_hash": "abc123...",
  "ext": ".py",
  "mtime": 1707456789.123,
  "size_bytes": 1234,
  "text_len": 500,
  "start_line": 1,
  "end_line": 120,
  "language": "python",
  "source": "repo",
  "repo_root": "/home/user/project"
}
```

## Nome Automático de Collection

Se `QDRANT_COLLECTION` não for definido, o nome é gerado automaticamente:

```
{QDRANT_COLLECTION_BASE}__{VECTOR_SIZE}__{slug(EMBEDDING_MODEL)}
```

Exemplo:
```
compass__3584__manutic_nomic_embed_code
```

Isso evita conflitos ao trocar de modelo (cada modelo terá sua própria collection).

## Idempotência

- `init`: Pode ser executado múltiplas vezes. Se a collection já existir com o mesmo vector_size, apenas valida.
- `index`: IDs são determinísticos. Reindexar o mesmo conteúdo não duplica pontos.

## Testes

```bash
cd apps/indexer
source .venv/bin/activate
pip install pytest
python -m pytest tests/ -v
```

## Troubleshooting

### "Erro no embedder: Falha ao obter vector size"

- Verifique se o Ollama está rodando: `curl http://localhost:11434`
- Verifique se o modelo está instalado: `ollama list`

### "Collection X tem vector size Y, mas embedding é size Z"

O modelo de embedding mudou. Opções:
1. Use `QDRANT_COLLECTION` para especificar outra collection
2. Delete a collection existente via API do Qdrant

### "Erro no Qdrant: conexão recusada"

- Verifique se o Qdrant está rodando: `curl http://localhost:6333`
