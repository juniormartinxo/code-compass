# Plano Atualizado: Evolução do Chunking do Code Compass

## Resumo

Evoluir o chunking atual do indexer de um modelo linear baseado em janelas de linhas para um modelo orientado a unidades semânticas de código, preservando compatibilidade incremental com o pipeline atual (`scan -> chunk_file -> embed -> upsert`) e preparando o sistema para:

1. identidade estável de chunk
2. indexação incremental real
3. metadados semânticos ricos
4. chunking por símbolo
5. suporte a perguntas de impacto, fluxo e navegação técnica

## Diagnóstico Atual

O estado atual do indexer apresenta três limitações centrais:

1. `chunkId` depende de `contentHash`, o que faz qualquer alteração textual mudar a identidade do chunk.
2. os chunks trafegam como `dict` ad-hoc, dificultando evolução segura do schema.
3. o chunking de código ainda é baseado em janelas lineares por linha, sem respeitar função, método, classe, componente ou bloco lógico.

Consequências:

* indexação incremental ineficiente
* churn excessivo no Qdrant
* dificuldade para enriquecer payloads
* recuperação semântica pobre para perguntas de engenharia

## Decisão Operacional Antes do Início

### Reindexação completa obrigatória

A introdução de `chunkId` estável incompatível com o formato antigo exige decisão explícita sobre o índice atual.

Decisão:

* a primeira versão com novo schema de chunk exigirá **reindexação completa obrigatória**
* os points antigos do Qdrant devem ser descartados ou substituídos por rebuild completo
* não haverá tentativa de compatibilidade entre IDs antigos e novos
* documentar isso no README, notas operacionais e fluxo de rollout do indexer

Justificativa:

* mais simples
* menos risco
* evita índice híbrido inconsistente
* mais adequado ao porte atual do projeto

### Versionamento de schema

Adicionar versionamento explícito do schema do chunk:

* `chunkSchemaVersion`
* valor inicial sugerido: `v2`

Objetivo:

* facilitar rollout
* permitir detecção de formato antigo no índice
* apoiar futuras migrações sem arqueologia manual

---

## Limitações Conhecidas por Etapa

1. **Estabilidade parcial do `chunkId` no Sprint 1**

   * Durante o uso de chunking linear por janela de linhas, o `chunkId` deixa de depender do `contentHash`, mas ainda pode mudar quando o arquivo sofre deslocamento estrutural de linhas, como inserção de conteúdo no início ou no meio do arquivo.
   * A estabilidade forte de identidade só é garantida após a adoção de chunking por símbolo nas Fases 5/6, quando `qualifiedSymbolName` e metadados estruturais passam a ancorar o chunk.

2. **Benefício de retrieval do `summaryText` só entra plenamente na Fase 9**

   * `summaryText` e `contextText` passam a ser gerados na Fase 3, mas seu benefício para retrieval/indexação só será realizado quando esses campos forem persistidos no payload do Qdrant e integrados ao pipeline de embedding/upsert na Fase 9.
   * Até lá, esses campos existem como preparação estrutural, sem impacto completo no índice.

---

## Sprint 1 — Fundação Estrutural

### Fase 1 + Fase 2 (fundidas no mesmo PR)

#### Objetivo da Fase 1 + Fase 2

Corrigir a identidade do chunk e introduzir um modelo explícito de dados no mesmo movimento, evitando retrabalho.

#### Entregas da Fase 1 + Fase 2

##### 1. Separação entre identidade e conteúdo

Substituir o modelo atual por:

* `chunkId`: identidade estrutural estável
* `contentHash`: hash do conteúdo atual

Regras iniciais para chunks lineares:

* `chunkId = sha256(path:start:end:language)`
* `contentHash = sha256(content_normalized)`

##### 2. Introdução de `ChunkDocument`

Criar um modelo explícito para chunks, com campos como:

* `chunkId`
* `contentHash`
* `chunkSchemaVersion`
* `path`
* `startLine`
* `endLine`
* `language`
* `content`
* `contentType`
* `symbolName`
* `qualifiedSymbolName`
* `symbolType`
* `parentSymbol`
* `signature`
* `imports`
* `exports`
* `callers`
* `callees`
* `summaryText`
* `contextText`
* `chunkStrategy`

##### 3. Serialização para payload do Qdrant

Padronizar a transformação de `ChunkDocument` para payload/indexação.

##### 4. Ajuste do `point id`

Atualizar a geração do point id no pipeline para refletir a nova identidade estável do chunk e não sua versão textual.

##### 5. Compatibilidade temporária do chunking atual

Manter o chunking linear atual como estratégia inicial (`chunkStrategy=line_window`) enquanto o schema novo entra em produção.

#### Arquivos-alvo

* `chunk.py`
* `__main__.py`
* eventual novo módulo de modelos (`chunk_models.py` ou equivalente)
* `test_chunk.py`

#### Critérios de aceitação

* o mesmo bloco estrutural mantém o mesmo `chunkId` após pequenas mudanças no conteúdo, desde que `start:end` permaneçam estáveis
* `contentHash` muda quando o conteúdo muda
* o pipeline continua funcionando de ponta a ponta
* o payload gerado fica mais rico e tipado
* testes refletem a nova identidade estável parcial do chunk linear

---

### Fase 3 — `summaryText` e `contextText`

#### Objetivo da Fase 3

Melhorar retrieval e preparar busca híbrida, sem ainda exigir chunking por símbolo.

#### Entregas da Fase 3

1. Adicionar `summaryText` a todos os chunks
2. Adicionar `contextText` a todos os chunks
3. Preparar o pipeline para futuramente embeddar `content` ou `summaryText + content`

#### Regras iniciais da Fase 3

##### `summaryText`

Deve conter informação lexical e estrutural útil, como:

* path
* language
* range de linhas
* primeira linha útil
* tipo do chunk
* nome de símbolo quando existir

##### `contextText`

Deve conter uma visão expandida do chunk, como:

* algumas linhas vizinhas
* ou, nesta fase inicial, uma composição simples do conteúdo com metadados próximos

#### Arquivos-alvo da Fase 3

* `chunk.py`
* `config.py`
* `embedder.py` se necessário

#### Critérios de aceitação da Fase 3

* todo chunk passa a carregar `summaryText` e `contextText`
* pipeline continua compatível
* payload interno fica preparado para hybrid retrieval futuro
* a equipe entende que o benefício pleno de retrieval desses campos só entra quando forem persistidos/indexados na Fase 9

---

## Sprint 2 — Enriquecimento Semântico Inicial

### Fase 4 — Classificação interna de conteúdo

#### Objetivo da Fase 4

Ir além do binário `code/docs` e diferenciar melhor os chunks.

#### Entregas da Fase 4

Adicionar `contentType` interno com valores como:

* `code_symbol`
* `code_context`
* `doc_section`
* `config_block`
* `sql_block`
* `test_case`

#### Estratégia inicial

* docs por extensão/path -> `doc_section`
* testes por nome/path -> `test_case`
* configs -> `config_block`
* SQL -> `sql_block`
* código comum -> `code_context` enquanto não houver parsing sintático

#### Arquivos-alvo da Fase 4

* `chunk.py`
* `__main__.py`
* testes de classificação

---

## Fase 5 — Chunking por símbolo para Python

### Objetivo da Fase 5

Parar de chunkar Python só por linha fixa e migrar para função/método/classe.

### Entregas da Fase 5

Implementar estratégia para Python usando AST nativo:

* função -> chunk
* método -> chunk
* classe pequena -> chunk único
* classe grande -> chunk-resumo + métodos
* fallback para `line_window` se parse falhar

### Metadados a extrair

* `symbolName`
* `qualifiedSymbolName`
* `symbolType`
* `parentSymbol`
* `signature`
* `startLine`
* `endLine`

#### Arquivos-alvo da Fase 5

* novo módulo tipo `chunk_python.py`
* `chunk.py`
* testes novos

---

## Sprint 3 — Chunking Estrutural Principal

### Fase 6 — Chunking por símbolo para TS / TSX / JS

#### Objetivo da Fase 6

Cobrir frontend/backend moderno com chunking semântico real.

#### Entregas da Fase 6

Suportar:

* função
* método
* componente React
* hook custom
* helper exportado
* classe pequena
* classe grande com resumo + métodos

#### Metadados

* `imports`
* `exports`
* `signature`
* `symbolName`
* `qualifiedSymbolName`

#### Fallback

* em falha de parse, usar `line_window`

#### Arquivos-alvo da Fase 6

* novo módulo tipo `chunk_ts.py`
* `chunk.py`
* fixtures TS/TSX
* testes

---

## Fase 7 — Grafo imediato de chamadas

### Objetivo da Fase 7

Dar suporte a perguntas de impacto e fluxo.

### Entregas da Fase 7

Adicionar:

* `callees`
* `callers`

Regras:

* grafo aproximado de 1 salto
* `callees` extraídos durante parse
* `callers` montados por índice reverso
* sem promessa de resolução perfeita de alias/dynamic dispatch

#### Arquivos-alvo da Fase 7

* módulos de chunk sintático
* módulo auxiliar de grafo
* testes específicos

---

## Sprint 4 — Conteúdo Não-Código + Pipeline Final

### Fase 8 — Estratégias específicas para docs, config e SQL

#### Objetivo da Fase 8

Parar de tratar docs/config/SQL como janelas genéricas.

#### Entregas da Fase 8

#### Markdown

* chunk por heading/subheading
* `contentType=doc_section`

#### Config

* chunk por seção/bloco
* `contentType=config_block`

#### SQL

* chunk por query ou bloco coerente
* `contentType=sql_block`

#### Arquivos-alvo da Fase 8

* módulos específicos por tipo
* `chunk.py`
* testes dedicados

---

### Fase 9 — Ajuste do pipeline de embedding e upsert

#### Objetivo da Fase 9

Fazer o pipeline usar os novos campos e consolidar indexação incremental.

#### Entregas da Fase 9

1. permitir escolher o campo usado no embedding:

   * `content`
   * ou `summaryText + content`

2. persistir no Qdrant:

   * `chunkSchemaVersion`
   * `contentType`
   * `symbolName`
   * `qualifiedSymbolName`
   * `symbolType`
   * `parentSymbol`
   * `callers`
   * `callees`
   * `chunkStrategy`
   * `summaryText`
   * `contextText`

3. usar identidade estável no upsert

#### Arquivos-alvo da Fase 9

* `__main__.py`
* `embedder.py`
* `qdrant_store.py`
* testes de payload/indexação

---

## Fase 10 — Reescrita da suíte de testes do chunker

### Objetivo da Fase 10

Fazer a suíte refletir chunking semântico, não só janela de linhas.

### Novos cenários obrigatórios

1. `chunkId` estável vs `contentHash` mutável
2. Python:

   * função
   * classe pequena
   * classe grande
3. TS/TSX:

   * componente
   * hook
   * helper
4. Markdown por heading
5. Config por seção
6. SQL por bloco coerente
7. `summaryText` e `contextText`
8. `callers` e `callees`
9. fallback heurístico
10. `contentType` correto
11. `chunkSchemaVersion` presente
12. reindex com schema novo exige rebuild completo

### Arquivos-alvo da Fase 10

* `test_chunk.py`
* novos fixtures
* testes de pipeline

---

## Ordem Final de Execução

### Sprint 1

* **Pré-requisito operacional**: documentar reindexação completa obrigatória
* **Fase 1 + Fase 2 juntas**
* **Fase 3**

### Sprint 2

* **Fase 4**
* **Fase 5**

### Sprint 3

* **Fase 6**
* **Fase 7**

### Sprint 4

* **Fase 8**
* **Fase 9**
* **Fase 10**

---

## Guardrails Arquiteturais

1. Não quebrar o pipeline atual de uma vez.
2. Manter fallback linear até o chunking por símbolo estar sólido.
3. Não usar `contentHash` como identidade estrutural.
4. Não trafegar chunks como `dict` solto se já houver `ChunkDocument`.
5. Não prometer resolução perfeita de grafo de chamadas.
6. Não tentar resolver todas as linguagens antes de Python + TS/TSX funcionarem bem.
7. A primeira mudança de schema exige rebuild completo do índice.

---

## Critério de Sucesso do Plano

Ao final da implementação:

* o índice deve aceitar reindex incremental real
* um mesmo símbolo deve manter identidade estável entre reindexações
* o sistema deve recuperar unidades de código, não apenas janelas lineares
* os payloads no Qdrant devem carregar metadados suficientes para perguntas de impacto, fluxo e navegação
* o chunker deve estar preparado para expandir contexto sem reescrever a base toda

---

## Decisão Resumida

As mudanças mais importantes continuam sendo:

1. **parar de usar `contentHash` dentro do `chunkId`**
2. **parar de chunkar código apenas por janelas lineares**

Com os ajustes incorporados:

* isso agora entra em um **Sprint 1 único e coerente**
* com **reindexação completa documentada desde o início**
* com **versionamento explícito do schema de chunk**
* e com **limitações conhecidas por etapa registradas de forma honesta**
