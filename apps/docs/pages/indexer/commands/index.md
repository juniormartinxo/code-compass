# Comando: index

Executa o pipeline completo de indexação: scan → chunk → embed → upsert.

## Uso

```bash
python -m indexer index [opções]
```

## Descrição

O comando `index` executa as seguintes etapas:

1. **Inicialização**: Probe do vector_size e validação/criação da collection
2. **Scan**: Escaneia o repositório para encontrar arquivos elegíveis
3. **Chunk**: Divide cada arquivo em chunks semânticos
4. **Embed**: Gera embeddings via provider HTTP configurado em batches
5. **Upsert**: Armazena vetores no Qdrant com IDs estáveis

### IDs Estáveis (Idempotência)

Os IDs dos pontos são determinísticos, compostos por:
- Caminho relativo do arquivo
- Índice do chunk
- Hash do conteúdo

Isso significa que reindexar o mesmo repositório:
- **Não duplica** pontos existentes
- **Atualiza** pontos cujo conteúdo mudou
- **Adiciona** pontos para arquivos novos

## Opções

| Opção | Descrição | Default |
|-------|-----------|---------|
| `--repo-root` | Caminho do repositório | Env: `REPO_ROOT` ou diretório pai |
| `--allow-exts` | Extensões permitidas (CSV) | `.ts,.tsx,.js,.jsx,.py,.md,.json,.yaml,.yml` |
| `--ignore-dirs` | Diretórios a ignorar (CSV) | `.git,node_modules,dist,build,...` |
| `--ignore-patterns` | Padrões glob para ignorar arquivos (CSV) | CLI > `SCAN_IGNORE_PATTERNS` > vazio |
| `--max-files` | Limite máximo de arquivos | Sem limite |
| `--chunk-lines` | Linhas por chunk | `120` |
| `--overlap-lines` | Overlap entre chunks | `20` |

## Variáveis de Ambiente

As variáveis são lidas do ambiente e carregadas automaticamente de `.env` e `.env.local` na raiz do repositório. `.env.local` sobrescreve `.env`, e variáveis já exportadas no shell têm precedência.

### Repositório e Chunking
- `REPO_ROOT`: Raiz do repositório
- `SCAN_IGNORE_DIRS`: Diretórios a ignorar
- `SCAN_ALLOW_EXTS`: Extensões permitidas
- `SCAN_IGNORE_PATTERNS`: Padrões glob para ignorar arquivos (ex.: `docs/**`, `**/*.test.ts`)
- `CHUNK_LINES`: Linhas por chunk
- `CHUNK_OVERLAP_LINES`: Overlap entre chunks

### Embeddings
- `EMBEDDING_PROVIDER_CODE`: Provider de embedding para `code`
- `EMBEDDING_PROVIDER_DOCS`: Provider de embedding para `docs`
- `EMBEDDING_PROVIDER_CODE_API_URL`: URL da API para `code`
- `EMBEDDING_PROVIDER_DOCS_API_URL`: URL da API para `docs`
- `EMBEDDING_PROVIDER_CODE_API_KEY`: API key para `code` (opcional no `ollama`)
- `EMBEDDING_PROVIDER_DOCS_API_KEY`: API key para `docs` (opcional no `ollama`)
- `EMBEDDING_MODEL_CODE`: Modelo de embedding para `code`
- `EMBEDDING_MODEL_DOCS`: Modelo de embedding para `docs`
- `EMBEDDING_BATCH_SIZE`: Textos por batch
- `EMBEDDING_MAX_RETRIES`: Máximo de tentativas
- `EMBEDDING_BACKOFF_BASE_MS`: Base para backoff exponencial

### Qdrant
- `QDRANT_URL`: URL do Qdrant
- `QDRANT_API_KEY`: API key (opcional)
- `QDRANT_COLLECTION_BASE`: Stem base das collections
- `QDRANT_DISTANCE`: Métrica de distância
- `QDRANT_UPSERT_BATCH`: Pontos por batch de upsert

## Saída

O comando retorna um JSON com estatísticas da indexação:

```json
{
  "status": "success",
  "repo_root": "/path/to/repo",
  "collections": {
    "code": "compass__manutic_nomic_embed__code",
    "docs": "compass__manutic_nomic_embed__docs"
  },
  "files_scanned": 42,
  "chunks_total": 156,
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

### Campos

| Campo | Descrição |
|-------|-----------|
| `status` | `success` ou `empty` (sem chunks) |
| `repo_root` | Caminho do repositório indexado |
| `collections` | Nomes das collections finais (`code` e `docs`) |
| `files_scanned` | Número de arquivos processados |
| `chunks_total` | Total de chunks gerados |
| `chunk_errors` | Erros durante chunking |
| `embeddings_generated` | Embeddings criados |
| `embeddings_generated_by_type` | Embeddings criados por tipo (`code`, `docs`) |
| `points_upserted` | Pontos inseridos/atualizados |
| `upsert_by_type` | Totais de upsert por tipo (`code`, `docs`) |
| `embedding` | Configuração efetiva por tipo (`provider`, `model`, `vector_size`) |
| `elapsed_ms` | Tempo total em milissegundos |
| `elapsed_sec` | Tempo total em segundos |

## Payload dos Pontos

Cada ponto no Qdrant contém o seguinte payload:

```json
{
  "repo": "my-repo",
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

Estes metadados permitem:
- **Filtros**: por extensão, linguagem, caminho
- **Escopo no MCP**: filtro por `repo` em `search_code`/`ask_code`
- **Rastreabilidade**: identificar origem do chunk
- **Debug**: verificar conteúdo e posição

## Exemplos

### Indexação básica

```bash
export REPO_ROOT=/path/to/my/project
python -m indexer index
```

### Multi-repo (code-base)

Para indexar todos os repos dentro de `code-base/`:

```bash
for repo in code-base/*; do
  [ -d "$repo" ] || continue
  python -m indexer index --repo-root "$repo"
done
```

> Atenção: `index` processa um único `repo_root` por execução e grava `payload.repo` com o nome desse diretório.  
> Se você executar com `--repo-root /.../code-base`, todos os pontos ficarão com `repo="code-base"` (sem distinguir os sub-repos).  
> Para multi-repo, execute por subdiretório (`code-base/<repo>`), como no exemplo acima.

### Com limite de arquivos (para testes)

```bash
python -m indexer index --repo-root /path/to/project --max-files 10
```

### Com chunks menores

```bash
python -m indexer index --chunk-lines 60 --overlap-lines 10
```

### Apenas TypeScript e Python

```bash
python -m indexer index --allow-exts .ts,.tsx,.py
```

## Logs

O comando emite logs informativos durante a execução:

```
2026-02-09 02:15:37,120 [INFO] Repo root: /path/to/repo
2026-02-09 02:15:37,120 [INFO] Embedding config [code]: provider=ollama model=manutic/nomic-embed-code api_url=http://localhost:11434
2026-02-09 02:15:37,121 [INFO] Embedding config [docs]: provider=ollama model=bge-m3 api_url=http://localhost:11434
2026-02-09 02:15:37,122 [INFO] Collections: code=compass__manutic_nomic_embed__code docs=compass__manutic_nomic_embed__docs
2026-02-09 02:15:37,120 [INFO] Iniciando scan...
2026-02-09 02:15:37,375 [INFO] Arquivos encontrados: 42
2026-02-09 02:15:37,378 [INFO] Total de chunks: 156
2026-02-09 02:15:40,580 [INFO] Embeddings gerados: 156
2026-02-09 02:15:40,634 [INFO] Indexação concluída: 156 pontos em 3.72s
```

## Performance

### Fatores que afetam o tempo

1. **Número de arquivos**: Mais arquivos = mais tempo de scan/chunk
2. **Tamanho do batch de embedding**: Batches maiores = menos requests, mas mais memória
3. **Tamanho do batch de upsert**: Batches maiores = menos roundtrips ao Qdrant
4. **Modelo de embedding**: Modelos maiores são mais lentos

### Recomendações

- Para repositórios grandes, comece com `--max-files` para testar
- Ajuste `EMBEDDING_BATCH_SIZE` baseado na memória disponível
- Use `QDRANT_UPSERT_BATCH=64` ou maior para melhor throughput

## Erros Comuns

### "Erro no embedder: Falha após N tentativas"

O Ollama está sobrecarregado ou indisponível.

**Solução:**
- Verifique se o Ollama está rodando
- Reduza `EMBEDDING_BATCH_SIZE`
- Aumente `EMBEDDING_MAX_RETRIES`

### "Erro no Qdrant: conexão recusada"

O Qdrant não está acessível.

**Solução:**
```bash
docker-compose -f infra/docker-compose.yml up -d qdrant
```

## Ver Também

- [init](./init.md) - Inicializa a collection no Qdrant
- [scan](./scan.md) - Escaneia arquivos do repositório
- [chunk](./chunk.md) - Divide arquivos em chunks
