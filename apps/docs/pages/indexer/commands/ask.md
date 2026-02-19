
# Code Compass Indexer - Ask Command

O comando `ask` implementa **RAG (Retrieval Augmented Generation)** — permite fazer perguntas em linguagem natural sobre o código indexado e receber respostas geradas pelo LLM configurado no MCP server.

## Visão Geral

O comando executa as seguintes etapas:
1. Gera embedding da pergunta usando o provider configurado
2. Busca chunks relevantes no Qdrant (como o `search`)
3. Lê o conteúdo dos arquivos encontrados
4. Monta um prompt com o contexto
5. Envia para o MCP server, que consulta o LLM configurado

## Uso Básico

```bash
python -m indexer ask "sua pergunta aqui" --scope-repo code-compass
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
| `--scope-repo` | - | Escopo explícito para um único repo |
| `--scope-repos` | - | Escopo explícito para múltiplos repos (CSV) |
| `--scope-all` | `false` | Escopo global (exige `ALLOW_GLOBAL_SCOPE=true` no MCP) |

### Variáveis de Ambiente

**LLM:**
| Variável | Default | Descrição |
|----------|---------|-----------|
| `LLM_MODEL` | `gpt-oss:latest` | Modelo LLM padrão para gerar respostas |

Precedência de configuração do modelo no `ask`: `--model` > `LLM_MODEL` > `gpt-oss:latest`.

**Embeddings:**
| Variável | Default | Descrição |
|----------|---------|-----------|
| `EMBEDDING_PROVIDER_CODE` | `ollama` | Provider de embedding para `code` |
| `EMBEDDING_PROVIDER_DOCS` | `ollama` | Provider de embedding para `docs` |
| `EMBEDDING_PROVIDER_CODE_API_URL` | `http://localhost:11434` | URL da API para `code` |
| `EMBEDDING_PROVIDER_DOCS_API_URL` | `http://localhost:11434` | URL da API para `docs` |
| `EMBEDDING_PROVIDER_CODE_API_KEY` | vazio | API key para `code` (opcional no `ollama`) |
| `EMBEDDING_PROVIDER_DOCS_API_KEY` | vazio | API key para `docs` (opcional no `ollama`) |
| `EMBEDDING_MODEL_CODE` | `manutic/nomic-embed-code` | Modelo de embedding para `code` |
| `EMBEDDING_MODEL_DOCS` | `bge-m3` | Modelo de embedding para `docs` |

**Qdrant:**
| Variável | Default | Descrição |
|----------|---------|-----------|
| `QDRANT_URL` | `http://localhost:6333` | URL do servidor Qdrant |
| `QDRANT_COLLECTION_BASE` | `compass__manutic_nomic_embed` | Stem base das collections |

> Dica operacional: para ambiente multi-repo, mantenha `QDRANT_COLLECTION_BASE` igual no indexer e no MCP server.

## Exemplos de Uso

### Pergunta Básica

```bash
python -m indexer ask "qual banco de dados vetorial é usado neste projeto?" --scope-repo code-compass
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
python -m indexer ask "como funciona o chunking?" --scope-repo code-compass --model deepseek-r1:32b
```

### Mostrar Fontes Consultadas

```bash
python -m indexer ask "qual a estrutura do projeto?" --scope-repo code-compass --show-context
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
python -m indexer ask "como fazer embeddings?" --scope-repo code-compass --ext .py
```

### Buscar em múltiplos repos

```bash
python -m indexer ask "onde estão os contratos compartilhados?" --scope-repos "repo-a,repo-b"
```

### Buscar em todos os repos (feature-flag)

```bash
python -m indexer ask "quais bibliotecas utilitárias existem?" --scope-all
```

No MCP server, habilite:

```bash
export ALLOW_GLOBAL_SCOPE=true
```

Sem essa env, `--scope-all` retorna erro `FORBIDDEN` no MCP.

### Mais Contexto

```bash
python -m indexer ask "explique a arquitetura completa" -k 10
```

### Output em JSON

```bash
python -m indexer ask "qual o propósito do indexer?" --scope-repo code-compass --json
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
│  (usuário)  │     │   (API)     │     │   (busca)   │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              v
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Resposta  │<────│     LLM     │<────│   Contexto  │
│   (texto)   │     │    (MCP)    │     │  (chunks)   │
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

Depende do provider configurado no MCP server (`LLM_MODEL_PROVIDER` + `LLM_MODEL_API_URL`).

```bash
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
| API de embedding indisponível | Exit code `1`, mensagem de erro |
| Modelo LLM não encontrado | Exit code `1`, mensagem de erro |
| Qdrant indisponível | Exit code `1`, mensagem de erro |
| Nenhum contexto encontrado | Mensagem informativa, exit code `0` |
| Arquivo fonte não existe mais | Usa placeholder `[arquivo não encontrado]` |

## Troubleshooting

### "Erro no embedder/LLM: Erro HTTP 404"
O modelo LLM não existe no provider configurado ou a URL está incorreta.

```bash
# Verificar URL configurada no MCP
echo "$LLM_MODEL_API_URL"

# Teste simples da API de embeddings (exemplo Ollama)
curl http://localhost:11434/api/tags
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
