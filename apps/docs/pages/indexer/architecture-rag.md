# Arquitetura RAG do Code Compass Indexer

Este documento explica como funciona o sistema de **Retrieval Augmented Generation (RAG)** implementado no comando `ask` do Indexer.

## Visão Geral

O RAG combina busca semântica com geração de linguagem natural para responder perguntas sobre o código-fonte. Em vez de o LLM "adivinhar" respostas, ele recebe o contexto relevante e responde baseado nele.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Pergunta   │────▶│  Embedding  │────▶│   Qdrant    │
│  (usuário)  │     │  (Ollama)   │     │   (busca)   │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Resposta   │◀────│     LLM     │◀────│  Contexto   │
│   (texto)   │     │  (Ollama)   │     │  (código)   │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Etapas do Fluxo RAG

### 1. Embedding da Pergunta

```
Entrada: "como funciona o chunking?"
Saída:   [0.12, -0.45, 0.78, ..., 0.33]  (vetor 3584-dim)
```

- Usa o mesmo modelo de embedding do indexador (`manutic/nomic-embed-code`)
- Transforma a pergunta em um vetor no mesmo espaço dos chunks indexados
- Permite comparar semanticamente a pergunta com o código

### 2. Busca no Qdrant (Banco Vetorial)

```
Entrada: vetor da pergunta
Saída:   5 chunks mais similares (metadados)
         - path: "indexer/chunk.py"
         - start_line: 20
         - end_line: 80
         - score: 0.87
```

**O que o Qdrant armazena:**
- Vetores de embedding (representação numérica do código)
- Metadados (path, linhas, hash, extensão, linguagem)

**O que o Qdrant NÃO armazena:**
- O texto/código em si (apenas referências)

**Por que usar busca vetorial?**
- Encontra resultados semanticamente similares, não apenas palavras exatas
- "como funciona chunking" encontra código sobre "dividir arquivos em blocos"

### 3. Leitura do Código (Filesystem)

```
Entrada: path="indexer/chunk.py", lines=20-80, repo_root="/home/user/project"
Saída:   conteúdo real do arquivo (linhas 20-80)
```

Com os metadados retornados pelo Qdrant, o sistema:
1. Monta o caminho completo: `{repo_root}/{path}`
2. Lê o arquivo do disco
3. Extrai apenas as linhas relevantes: `lines[start_line:end_line]`

**Por que ler do disco?**
- Garante que o contexto é sempre atualizado
- O Qdrant só precisa armazenar referências (menor uso de memória)
- Se o arquivo foi modificado desde a indexação, precisa reindexar

### 4. Montagem do Prompt

O sistema monta um prompt estruturado para o LLM:

```
SYSTEM:
Você é um assistente especializado em analisar código-fonte.
Responda às perguntas do usuário baseando-se APENAS no contexto fornecido.
Se a informação não estiver no contexto, diga que não encontrou essa informação.
Seja conciso e direto. Responda em português brasileiro.

USER:
## Contexto do código-fonte:

### Arquivo 1: indexer/chunk.py (linhas 20-80)
```python
def chunk_lines(lines: list[str], chunk_size: int, overlap: int) -> list[tuple]:
    """Divide linhas em chunks com overlap."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be < chunk_size")
    ...
```

### Arquivo 2: apps/docs/pages/indexer/commands/chunk.md (linhas 1-50)
```markdown
# Comando Chunk
O comando chunk divide arquivos em pedaços...
```

## Pergunta:
como funciona o chunking?

## Resposta:
```

### 5. Geração de Resposta (LLM)

```
Entrada: prompt montado com contexto
Saída:   resposta em linguagem natural
```

O LLM (ex: `qwen3-coder:30b`, `gpt-oss:latest`):
- Lê o contexto fornecido
- Entende a pergunta
- Sintetiza uma resposta baseada apenas no que viu

**O LLM não:**
- Acessa arquivos diretamente
- Busca no Qdrant
- Inventa informações (idealmente)

## Componentes e Responsabilidades

| Componente | Responsabilidade | Armazena |
|------------|------------------|----------|
| **Ollama Embedding** | Converte texto → vetor | - |
| **Qdrant** | Busca vetores similares | Vetores + metadados |
| **Filesystem** | Fornece código real | Arquivos fonte |
| **Ollama LLM** | Gera resposta | - |

## Fluxo de Dados Detalhado

```
┌────────────────────────────────────────────────────────────────────┐
│                         INDEXAÇÃO (index)                          │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Arquivos ──▶ Chunks ──▶ Embeddings ──▶ Qdrant                    │
│  (disco)     (texto)     (vetores)      (armazena vetores +       │
│                                          metadados)               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│                         CONSULTA (ask)                             │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Pergunta ──▶ Embedding ──▶ Qdrant ──▶ Metadados                   │
│  (texto)      (vetor)       (busca)    (paths + linhas)           │
│                                              │                     │
│                                              ▼                     │
│                              Filesystem ──▶ Código Real            │
│                              (leitura)      (contexto)             │
│                                              │                     │
│                                              ▼                     │
│                              LLM ──▶ Resposta                      │
│                              (geração)                             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Por que RAG é Melhor que LLM Puro?

| Aspecto | LLM Puro | RAG |
|---------|----------|-----|
| **Conhecimento** | Limitado ao treinamento | Atualizado com código atual |
| **Alucinações** | Pode inventar código | Responde baseado em contexto real |
| **Especificidade** | Genérico | Específico para seu projeto |
| **Citações** | Não consegue citar fontes | Indica arquivos e linhas exatas |
| **Privacidade** | Código pode vazar no treinamento | Código nunca sai do ambiente local |

## Limitações e Considerações

### 1. Qualidade depende da indexação
- Se o código relevante não foi indexado, não será encontrado
- Reindexar após mudanças significativas

### 2. Limite de contexto
- LLMs têm limite de tokens (ex: 8K, 32K)
- Muitos chunks podem exceder o limite
- Use `-k` para ajustar quantidade de contexto

### 3. Similaridade ≠ Relevância
- Alta similaridade vetorial não garante relevância perfeita
- Reformule a pergunta se resultados não forem bons

### 4. Código atualizado vs indexado
- Se o arquivo mudou após indexação, o contexto pode estar desatualizado
- O sistema lê do disco, mas o Qdrant pode apontar para linhas antigas

## Exemplo Completo

**Pergunta:**
```bash
python -m indexer ask "qual banco de dados vetorial é usado neste projeto?"
```

**Logs (o que acontece):**
```
[INFO] Pergunta: qual banco de dados vetorial é usado neste projeto?
[INFO] LLM Model: gpt-oss:latest

# 1. Embedding da pergunta
[INFO] HTTP POST http://localhost:11434/api/embed → 200 OK
[INFO] Vetor size: 3584

# 2. Busca no Qdrant
[INFO] HTTP POST http://localhost:6333/.../query → 200 OK
[INFO] Chunks encontrados: 5

# 3. Leitura dos arquivos (interno, não logado)

# 4. Chamada ao LLM
[INFO] Chamando LLM...
[INFO] HTTP POST http://localhost:11434/api/chat → 200 OK
```

**Resposta:**
```
💬 **Pergunta:** qual banco de dados vetorial é usado neste projeto?

🤖 **Resposta:**
O banco de dados vetorial usado neste projeto é o **Qdrant**.

📚 **Fontes consultadas:**
  1. apps/docs/pages/ADRs/ADR-02.md (linhas 1-120) - score: 0.8495
  2. .agents/skills/developer-vector-db/SKILL.md (linhas 1-67) - score: 0.8321

⏱️  Tempo: 15.32s | Modelo: gpt-oss:latest
```

## Ver Também

- [Comando ask](./commands/ask.md) - Uso do comando RAG
- [Comando search](./commands/search.md) - Busca semântica sem LLM
- [Comando index](./commands/index.md) - Indexação de código
