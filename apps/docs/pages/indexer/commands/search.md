
# Code Compass Indexer - Search Command

O comando `search` permite realizar **busca semântica** na collection de código indexado, encontrando chunks relevantes baseado na similaridade vetorial.

## Visão Geral

O comando:
1. Gera um embedding da query usando o Ollama
2. Busca os vetores mais similares no Qdrant
3. Retorna os chunks mais relevantes com score de similaridade e snippet contextual

## Uso Básico

```bash
python -m indexer search "sua query aqui"
```

### Opções Configuráveis

| Opção | Default | Descrição |
|-------|---------|-----------|
| `query` | - | Texto da busca (obrigatório) |
| `-k`, `--top-k`, `--topk` | `10` | Número de resultados a retornar |
| `--ext` | - | Filtrar por extensão (ex: `.py`) |
| `--language` | - | Filtrar por linguagem (ex: `python`) |
| `--json` | `false` | Output em formato JSON |

### Variáveis de Ambiente

O comando utiliza as mesmas variáveis de ambiente do `init` e `index`:

**Embeddings (Ollama):**
| Variável | Default | Descrição |
|----------|---------|-----------|
| `OLLAMA_URL` | `http://localhost:11434` | URL do servidor Ollama |
| `EMBEDDING_MODEL` | `manutic/nomic-embed-code` | Modelo de embedding |

**Qdrant:**
| Variável | Default | Descrição |
|----------|---------|-----------|
| `QDRANT_URL` | `http://localhost:6333` | URL do servidor Qdrant |
| `QDRANT_API_KEY` | - | API key (opcional) |
| `QDRANT_COLLECTION_BASE` | `compass` | Base para nome da collection |
| `QDRANT_COLLECTION` | - | Nome explícito da collection |

> Dica operacional: para evitar mismatch entre indexação e consulta, prefira definir `QDRANT_COLLECTION` explicitamente.
>
> Se `QDRANT_API_KEY` estiver vazia (`QDRANT_API_KEY=`), o cliente não envia API key. Isso é útil em ambiente local com `http://` para evitar warnings de conexão insegura.

## Exemplos de Uso

### Busca Básica

```bash
python -m indexer search "como fazer chunking de arquivos"
```

**Saída:**
```
🔍 Query: "como fazer chunking de arquivos"
📊 5 resultado(s):

  1. [0.7879] .agents/skills/developer-indexer/references/checklist.md
     📍 Linhas: 1-21 | Extensão: .md

  2. [0.7864] .agents/skills/architect/SKILL.md
     📍 Linhas: 101-131 | Extensão: .md
  ...
```

### Filtrar por Extensão

```bash
python -m indexer search "embedding" --ext .py
```

### Mais Resultados

```bash
python -m indexer search "qdrant vector store" -k 10
```

### Output em JSON

```bash
python -m indexer search "scan files" --json
```

**Saída JSON:**
```json
[
  {
    "id": "e32d7eef-41a1-51da-bd18-fc2e597ae68b",
    "score": 0.8241242,
    "payload": {
      "path": "src/main.py",
      "chunk_index": 0,
      "content_hash": "abc123...",
      "ext": ".py",
      "start_line": 1,
      "end_line": 120,
      "language": "python"
    }
  }
]
```

### Filtrar por Linguagem

```bash
python -m indexer search "class definition" --language python
```

## Detalhes de Implementação

### Geração de Embedding
O comando usa o mesmo modelo de embedding configurado para indexação (`EMBEDDING_MODEL`). Isso garante que a query seja representada no mesmo espaço vetorial dos chunks indexados.

### Resolução da Collection
O nome da collection é resolvido automaticamente baseado em:
- `QDRANT_COLLECTION` (se definido explicitamente)
- Ou gerado: `{QDRANT_COLLECTION_BASE}__{vector_size}__{model_slug}`

### Score de Similaridade
O score retornado é a **similaridade de cosseno** (ou outra métrica configurada via `QDRANT_DISTANCE`):
- `1.0` = idêntico
- `0.0` = sem relação
- Valores típicos para resultados relevantes: `0.7+`

### Snippet e identificação do projeto

No output textual do `search`, cada resultado é exibido com:

- Cabeçalho no formato `[repo] path:start_line-end_line` quando o payload inclui `repo`
- `snippet` com prioridade para `payload.text`
- Fallback automático: se `payload.text` não existir, o CLI tenta reconstruir o trecho lendo o arquivo em `repo_root + path` usando `start_line`/`end_line`

Se não for possível extrair trecho (ex.: arquivo não acessível), o output mantém `"(no text payload)"`.

### Filtros
Os filtros são aplicados diretamente no Qdrant, permitindo refinar resultados sem recalcular embeddings:
- `--ext`: Match exato na extensão (ex: `.py`)
- `--language`: Match exato na linguagem detectada (ex: `python`)

## Comportamento de Erro

| Cenário | Comportamento |
|---------|---------------|
| Ollama indisponível | Exit code `1`, mensagem de erro |
| Qdrant indisponível | Exit code `1`, mensagem de erro |
| Collection não existe | Exit code `1`, mensagem de erro |
| Nenhum resultado | Lista vazia, exit code `0` |

## Troubleshooting

### "Erro no embedder: Falha ao obter vector size"
O Ollama não está acessível ou o modelo não está instalado.

```bash
# Verificar Ollama
curl http://localhost:11434

# Verificar modelo
ollama list

# Instalar modelo se necessário
ollama pull manutic/nomic-embed-code
```

### "Erro no Qdrant: conexão recusada"
O Qdrant não está rodando.

```bash
# Iniciar Qdrant
docker-compose -f infra/docker-compose.yml up -d qdrant
```

### Resultados não relevantes
- Verifique se o repositório foi indexado corretamente (`python -m indexer index`)
- Tente aumentar `-k` para ver mais resultados
- Use filtros para refinar (ex: `--ext .py`)

## Ver Também

- [init](./init.md) - Inicializa a collection no Qdrant
- [index](./index.md) - Indexa o repositório
- [ask](./ask.md) - Perguntas em linguagem natural (RAG)
- [chunk](./chunk.md) - Divide arquivos em chunks
