# Comando: init

Inicializa a collection no Qdrant para armazenamento de vetores.

## Uso

```bash
python -m indexer init [opções]
```

## Descrição

O comando `init` prepara o ambiente para indexação:

1. **Probe do Vector Size**: Conecta ao provider de embedding e descobre automaticamente o tamanho do vetor para `code` e `docs`
2. **Resolução dos Nomes**: Gera os nomes das collections de `code` e `docs`
3. **Criação/Validação**: Cria as collections no Qdrant (se não existirem) ou valida as existentes

### Comportamento Idempotente

Este comando pode ser executado múltiplas vezes sem efeitos colaterais:
- Se a collection não existir, será criada
- Se já existir com o mesmo vector_size, apenas valida
- Se existir com vector_size diferente, falha com erro claro

## Opções

| Opção | Descrição | Default |
|-------|-----------|---------|
| `--api-url-code` | URL da API de embedding para `code` | env: `EMBEDDING_PROVIDER_CODE_API_URL` |
| `--api-url-docs` | URL da API de embedding para `docs` | env: `EMBEDDING_PROVIDER_DOCS_API_URL` |
| `--api-key-code` | API key do provider para `code` | env: `EMBEDDING_PROVIDER_CODE_API_KEY` |
| `--api-key-docs` | API key do provider para `docs` | env: `EMBEDDING_PROVIDER_DOCS_API_KEY` |
| `--provider-code` | Provider de embedding para `code` | `ollama` (env: `EMBEDDING_PROVIDER_CODE`) |
| `--provider-docs` | Provider de embedding para `docs` | `ollama` (env: `EMBEDDING_PROVIDER_DOCS`) |
| `--model-code` | Modelo de embedding para `code` | `manutic/nomic-embed-code` (env: `EMBEDDING_MODEL_CODE`) |
| `--model-docs` | Modelo de embedding para `docs` | `bge-m3` (env: `EMBEDDING_MODEL_DOCS`) |
| `--qdrant-url` | URL do servidor Qdrant | `http://localhost:6333` (env: `QDRANT_URL`) |

## Variáveis de Ambiente

As variáveis são lidas do ambiente e carregadas automaticamente de `.env` e `.env.local` na raiz do repositório. `.env.local` sobrescreve `.env`, e variáveis já exportadas no shell têm precedência.

- `EMBEDDING_PROVIDER_CODE`: Provider de embedding para `code`
- `EMBEDDING_PROVIDER_DOCS`: Provider de embedding para `docs`
- `EMBEDDING_PROVIDER_CODE_API_URL`: URL da API de embedding para `code`
- `EMBEDDING_PROVIDER_DOCS_API_URL`: URL da API de embedding para `docs`
- `EMBEDDING_PROVIDER_CODE_API_KEY`: API key do provider para `code` (opcional no `ollama`)
- `EMBEDDING_PROVIDER_DOCS_API_KEY`: API key do provider para `docs` (opcional no `ollama`)
- `EMBEDDING_MODEL_CODE`: Modelo de embedding para `code`
- `EMBEDDING_MODEL_DOCS`: Modelo de embedding para `docs`
- `QDRANT_URL`: URL do Qdrant
- `QDRANT_API_KEY`: API key do Qdrant (opcional)
- `QDRANT_COLLECTION_BASE`: Stem base das collections
- `QDRANT_DISTANCE`: Métrica de distância (COSINE, EUCLID, DOT)

## Saída

O comando retorna um JSON com informações da inicialização:

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
      "name": "compass__manutic_nomic_embed__code",
      "action": "created"
    },
    "docs": {
      "name": "compass__manutic_nomic_embed__docs",
      "action": "created"
    }
  },
  "distance": "COSINE",
  "qdrant_url": "http://localhost:6333"
}
```

### Campos

| Campo | Descrição |
|-------|-----------|
| `embedding` | Configuração por tipo (`provider`, `api_url`, `model`, `vector_size`) |
| `collections` | Mapa com collections finais (`code` e `docs`) e ação (`created`/`validated`) |
| `distance` | Métrica de distância configurada |
| `qdrant_url` | URL do Qdrant usado |

## Geração Automática de Nome

O stem base é o valor de `QDRANT_COLLECTION_BASE`:

```
{QDRANT_COLLECTION_BASE}
```

Exemplo para o modelo padrão:
```
compass__manutic_nomic_embed
```

Os nomes finais usados no Qdrant são:

- `{QDRANT_COLLECTION_BASE}__code`
- `{QDRANT_COLLECTION_BASE}__docs`

## Exemplos

### Inicialização básica

```bash
python -m indexer init
```

### Com URLs customizadas

```bash
python -m indexer init \
  --api-url-code http://ollama.local:11434 \
  --api-url-docs http://ollama.local:11434 \
  --qdrant-url http://qdrant.local:6333
```

## Erros Comuns

### "Erro no embedder: Falha ao obter vector size"

A API do provider de embedding não está acessível ou o modelo não está disponível.

**Solução:**
```bash
# Verificar API (exemplo Ollama)
curl http://localhost:11434/api/tags

# Instalar modelos
ollama pull manutic/nomic-embed-code
ollama pull bge-m3
```

### "Collection X tem vector size Y, mas embedding é size Z"

A collection já existe mas foi criada com outro modelo de embedding.

**Solução:**
- Use outro `QDRANT_COLLECTION_BASE`
- Ou delete a collection existente

## Ver Também

- [index](./index.md) - Executa a indexação completa
- [scan](./scan.md) - Escaneia arquivos do repositório
- [chunk](./chunk.md) - Divide arquivos em chunks
