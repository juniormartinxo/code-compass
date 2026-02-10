
# Code Compass Indexer - Ask Command

O comando `ask` implementa **RAG (Retrieval Augmented Generation)** — permite fazer perguntas em linguagem natural sobre o código indexado e receber respostas geradas por um LLM local.

## Visão Geral

O comando executa as seguintes etapas:
1. Gera embedding da pergunta usando Ollama
2. Busca chunks relevantes no Qdrant (como o `search`)
3. Lê o conteúdo dos arquivos encontrados
4. Monta um prompt com o contexto
5. Envia para um LLM local (Ollama) gerar a resposta

## Uso Básico

```bash
python -m indexer ask "sua pergunta aqui"
```

### Opções Configuráveis

| Opção | Default | Descrição |
|-------|---------|-----------|
| `question` | - | Pergunta em linguagem natural (obrigatório) |
| `-k`, `--top-k` | `5` | Número de chunks de contexto |
| `--model` | `gpt-oss:latest` | Modelo LLM para resposta |
| `--ext` | - | Filtrar contexto por extensão (ex: `.py`) |
| `--min-score` | `0.6` | Score mínimo de similaridade para usar chunk no contexto |
| `--show-context` | `false` | Mostrar fontes consultadas |
| `--json` | `false` | Output em formato JSON |

### Variáveis de Ambiente

**LLM:**
| Variável | Default | Descrição |
|----------|---------|-----------|
| `LLM_MODEL` | `gpt-oss:latest` | Modelo LLM para gerar respostas |

**Embeddings (Ollama):**
| Variável | Default | Descrição |
|----------|---------|-----------|
| `OLLAMA_URL` | `http://localhost:11434` | URL do servidor Ollama |
| `EMBEDDING_MODEL` | `manutic/nomic-embed-code` | Modelo de embedding |

**Qdrant:**
| Variável | Default | Descrição |
|----------|---------|-----------|
| `QDRANT_URL` | `http://localhost:6333` | URL do servidor Qdrant |
| `QDRANT_COLLECTION_BASE` | `compass` | Base para nome da collection |

## Exemplos de Uso

### Pergunta Básica

```bash
python -m indexer ask "qual banco de dados vetorial é usado neste projeto?"
```

**Saída:**
```
💬 **Pergunta:** qual banco de dados vetorial é usado neste projeto?

🤖 **Resposta:**
O banco de dados vetorial usado neste projeto é o **Qdrant**.

⏱️  Tempo: 15.32s | Modelo: gpt-oss:latest
```

### Com Modelo Específico

```bash
python -m indexer ask "como funciona o chunking?" --model deepseek-r1:32b
```

### Mostrar Fontes Consultadas

```bash
python -m indexer ask "qual a estrutura do projeto?" --show-context
```

**Saída:**
```
💬 **Pergunta:** qual a estrutura do projeto?

🤖 **Resposta:**
O projeto Code Compass é organizado em...

📚 **Fontes consultadas:**
  1. apps/docs/pages/ADRs/ADR-02.md (linhas 1-120) - score: 0.8495
  2. .agents/skills/architect/SKILL.md (linhas 1-67) - score: 0.8321
  ...

⏱️  Tempo: 22.15s | Modelo: gpt-oss:latest
```

### Filtrar por Extensão

```bash
python -m indexer ask "como fazer embeddings?" --ext .py
```

### Mais Contexto

```bash
python -m indexer ask "explique a arquitetura completa" -k 10
```

### Output em JSON

```bash
python -m indexer ask "qual o propósito do indexer?" --json
```

**Saída JSON:**
```json
{
  "question": "qual o propósito do indexer?",
  "answer": "O indexer é responsável por...",
  "model": "gpt-oss:latest",
  "contexts_used": 5,
  "elapsed_sec": 18.45,
  "sources": [
    {
      "path": "apps/indexer/README.md",
      "lines": "1-50",
      "score": 0.8654
    }
  ]
}
```

## Detalhes de Implementação

### Fluxo RAG Completo

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Pergunta  │────>│  Embedding  │────>│   Qdrant    │
│  (usuário)  │     │  (Ollama)   │     │   (busca)   │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              v
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Resposta  │<────│     LLM     │<────│   Contexto  │
│   (texto)   │     │  (Ollama)   │     │  (chunks)   │
└─────────────┘     └─────────────┘     └─────────────┘
```

### System Prompt

O LLM recebe o seguinte prompt de sistema:
```
Você é um assistente especializado em analisar código-fonte.
Responda às perguntas do usuário baseando-se APENAS no contexto fornecido.
Se a informação não estiver no contexto, diga que não encontrou essa informação no código indexado.
Seja conciso e direto. Responda em português brasileiro.
```

### Leitura de Contexto

Os chunks encontrados são lidos diretamente do sistema de arquivos usando:
- `repo_root` do payload (onde o repositório foi indexado)
- `path` relativo do arquivo
- `start_line` e `end_line` para extrair apenas o trecho relevante

### Modelos LLM Suportados

Qualquer modelo instalado no Ollama pode ser usado:

```bash
# Listar modelos disponíveis
ollama list

# Exemplos de uso
python -m indexer ask "pergunta" --model gpt-oss:latest
python -m indexer ask "pergunta" --model deepseek-r1:32b
python -m indexer ask "pergunta" --model qwen3-coder:30b
```

## Performance

### Fatores que Afetam o Tempo

| Fator | Impacto |
|-------|---------|
| Tamanho do modelo LLM | Modelos maiores = mais lento |
| Número de chunks (`-k`) | Mais contexto = prompt maior |
| Complexidade da pergunta | Respostas longas = mais tempo |
| Hardware (GPU/CPU) | GPU acelera significativamente |

### Recomendações

- Para respostas rápidas: use modelos menores (`gpt-oss:latest`, `qwen:7b`)
- Para respostas melhores: use modelos maiores (`deepseek-r1:32b`, `qwen3-coder:30b`)
- Para código: use modelos especializados (`qwen3-coder`, `deepseek-coder`)

## Comportamento de Erro

| Cenário | Comportamento |
|---------|---------------|
| Ollama indisponível | Exit code `1`, mensagem de erro |
| Modelo LLM não encontrado | Exit code `1`, mensagem de erro |
| Qdrant indisponível | Exit code `1`, mensagem de erro |
| Nenhum contexto encontrado | Mensagem informativa, exit code `0` |
| Arquivo fonte não existe mais | Usa placeholder `[arquivo não encontrado]` |

## Troubleshooting

### "Erro no embedder/LLM: Erro HTTP 404"
O modelo LLM especificado não está instalado.

```bash
# Verificar modelos instalados
ollama list

# Instalar modelo
ollama pull gpt-oss:latest
```

### Resposta muito genérica ou "não encontrei"
- Verifique se o repositório foi indexado: `python -m indexer index`
- Aumente o número de chunks: `-k 10`
- Reformule a pergunta de forma mais específica

### Timeout na resposta
Modelos grandes podem demorar. Alternativas:
- Use um modelo menor: `--model gpt-oss:latest`
- Reduza o contexto: `-k 3`

### Contexto não relevante
- Use filtros: `--ext .py` para focar em código Python
- Reindexe com filtros mais específicos no `index`
- Aumente `--min-score` (ex: `0.75`) para reduzir chunks fracos
- Garanta que sua indexação ignore ambientes/cache (`.venv`, `venv`, `__pycache__`)

## Comparação: search vs ask

| Aspecto | `search` | `ask` |
|---------|----------|-------|
| **Saída** | Lista de chunks com scores | Resposta em linguagem natural |
| **Uso do LLM** | Não | Sim |
| **Tempo** | ~1-2s | ~10-60s (depende do modelo) |
| **Quando usar** | Encontrar arquivos/trechos | Entender o código |

## Ver Também

- [Arquitetura RAG](../architecture-rag.md) - Como funciona o RAG internamente
- [search](./search.md) - Busca semântica (sem LLM)
- [init](./init.md) - Inicializa a collection no Qdrant
- [index](./index.md) - Indexa o repositório
- [chunk](./chunk.md) - Divide arquivos em chunks
