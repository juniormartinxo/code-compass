# Comando: init

Inicializa a collection no Qdrant para armazenamento de vetores.

## Uso

```bash
python -m indexer init [opções]
```

## Descrição

O comando `init` prepara o ambiente para indexação:

1. **Probe do Vector Size**: Conecta ao Ollama e descobre automaticamente o tamanho do vetor do modelo configurado
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
| `--ollama-url` | URL do servidor Ollama | `http://localhost:11434` (env: `OLLAMA_URL`) |
| `--model` | Modelo de embedding | `manutic/nomic-embed-code` (env: `EMBEDDING_MODEL`) |
| `--qdrant-url` | URL do servidor Qdrant | `http://localhost:6333` (env: `QDRANT_URL`) |

## Variáveis de Ambiente

As variáveis são lidas do ambiente e carregadas automaticamente de `.env` e `.env.local` na raiz do repositório. `.env.local` sobrescreve `.env`, e variáveis já exportadas no shell têm precedência.

- `OLLAMA_URL`: URL do Ollama
- `EMBEDDING_MODEL`: Modelo de embedding
- `QDRANT_URL`: URL do Qdrant
- `QDRANT_API_KEY`: API key do Qdrant (opcional)
- `QDRANT_COLLECTION_BASE`: Stem base das collections
- `QDRANT_DISTANCE`: Métrica de distância (COSINE, EUCLID, DOT)

## Saída

O comando retorna um JSON com informações da inicialização:

```json
{
  "provider": "ollama",
  "ollama_url": "http://localhost:11434",
  "model": "manutic/nomic-embed-code",
  "vector_size": 3584,
  "collections": {
    "code": {
      "name": "compass__3584__manutic_nomic_embed__code",
      "action": "created"
    },
    "docs": {
      "name": "compass__3584__manutic_nomic_embed__docs",
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
| `provider` | Provider de embeddings (`ollama`) |
| `ollama_url` | URL do Ollama usado |
| `model` | Modelo de embedding |
| `vector_size` | Tamanho do vetor descoberto |
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
compass__3584__manutic_nomic_embed_code
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
  --ollama-url http://ollama.local:11434 \
  --qdrant-url http://qdrant.local:6333
```

## Erros Comuns

### "Erro no embedder: Falha ao obter vector size"

O Ollama não está acessível ou o modelo não está instalado.

**Solução:**
```bash
# Verificar Ollama
curl http://localhost:11434

# Instalar modelo
ollama pull manutic/nomic-embed-code
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
