# Plano Final de Integração do Tree-sitter no Code Compass

## Resumo

Este plano substitui a base atual de parsing semântico de código do indexer por Tree-sitter, preservando o pipeline `scan -> chunk -> embed -> upsert -> search`, mantendo o contrato público do payload e preparando o Code Compass para expansão multi-linguagem sem reintroduzir acoplamento em `chunk.py`.

Decisões fechadas:
1. o backend final de parsing de código será `tree_sitter`
2. a primeira entrega funcional cobre:
   - `python`
   - `typescript`
   - `typescriptreact`
   - `javascript`
   - `javascriptreact`
3. `docs`, `config` e `sql` permanecem com os chunkers especializados atuais
4. o rollout sobe o schema de `v5` para `v6`, com rebuild completo obrigatório
5. haverá backend `legacy` temporário como escape hatch operacional
6. a arquitetura deve permitir adicionar nova linguagem sem alterar [chunk.py](/apps/indexer/indexer/chunk.py)
7. o plano inclui baseline, benchmark, observabilidade, rollback, regressão estrutural e validação MCP

## Objetivo

Trocar o parsing atual por Tree-sitter para:
1. reduzir fragilidade heurística, principalmente em `TS/TSX/JS`
2. unificar a fundação de parsing semântico de código
3. preparar expansão futura para outras linguagens
4. preservar o shape do payload já usado por indexação, busca e MCP
5. tornar a terceira linguagem barata de adicionar

## Fora de Escopo

1. migrar `markdown`, `config` ou `sql` para Tree-sitter neste ciclo
2. entregar suporte semântico completo a Go, Rust ou Java neste ciclo
3. alterar contrato público do MCP
4. redesenhar o payload do Qdrant além do necessário para `v6`
5. remover o backend `legacy` neste mesmo trabalho

## Estado Atual

Hoje o indexer usa:
1. `ast` nativo para Python em [chunk_python.py](/apps/indexer/indexer/chunk_python.py)
2. parser heurístico com regex e balanceamento estrutural para TS/TSX/JS em [chunk_ts.py](/apps/indexer/indexer/chunk_ts.py)
3. dispatch manual por linguagem em [chunk.py](/apps/indexer/indexer/chunk.py)
4. schema atual `v5` em [chunk_models.py](/apps/indexer/indexer/chunk_models.py)

Problemas atuais:
1. alto custo de manutenção do parser heurístico
2. acoplamento de `chunk.py` a linguagens específicas
3. baixa previsibilidade para adicionar novas linguagens
4. pouca observabilidade sobre fallback, cobertura e custo do parsing
5. falta de contrato formal para adapters

## Mudanças de Interface e Contrato

### Mudanças explícitas

1. adicionar `CODE_CHUNK_PARSER_BACKEND=tree_sitter|legacy` em [config.py](/apps/indexer/indexer/config.py)
2. subir `CHUNK_SCHEMA_VERSION` de `v5` para `v6` em [chunk_models.py](/apps/indexer/indexer/chunk_models.py)
3. adicionar logs estruturados de parsing e fallback no runtime do indexer
4. documentar rebuild completo obrigatório e rollback operacional

### Mudanças que não serão feitas

1. não renomear estratégias públicas existentes:
   - `python_symbol`
   - `ts_symbol`
   - `line_window`
2. não remover campos atuais do payload
3. não persistir estado de fallback no Qdrant
4. não usar auto-discovery de adapters nesta primeira versão
5. não adicionar novo comando público de benchmark ao CLI do indexer

## Estratégia de Dependências e Compatibilidade

### Dependências novas

Adicionar em [requirements.txt](/apps/indexer/requirements.txt):
1. binding principal do Tree-sitter
2. grammar package de Python
3. grammar package de TypeScript/TSX
4. grammar package de JavaScript/JSX, se separado

### Política de versionamento

1. fixar versões exatas dos bindings e grammars
2. documentar matriz de compatibilidade mínima em [apps/indexer/README.md](/apps/indexer/README.md)
3. validar em runtime:
   - grammar presente
   - versão instalada igual à versão pinada
   - linguagem esperada carregável
4. falhar cedo se backend `tree_sitter` estiver ativo e alguma grammar estiver ausente ou incompatível

### Decisão sobre versionamento

Não haverá política de “versão mínima aberta”. O plano usa pinagem exata por ciclo para reduzir drift.

## Arquitetura Proposta

## 1. Pacote interno `tree_sitter/`

Criar `apps/indexer/indexer/tree_sitter/` com:

1. `runtime.py`
   - carrega grammars
   - instancia e reutiliza `Language`
   - instancia e reutiliza `Parser`
   - compila e reutiliza queries
   - valida registry e compatibilidade de versions
   - expõe helpers de bytes, ranges e texto
   - expõe helper de debug de queries para testes e troubleshooting

2. `types.py`
   - define `SyntaxChunkSpec`
   - define `LanguageAdapter`
   - define `QuerySet`

3. `registry.py`
   - registry explícita e tipada de linguagens para adapters

4. `adapters/python.py`
   - adapter Tree-sitter para Python

5. `adapters/typescript.py`
   - adapter Tree-sitter para TS/TSX/JS/JSX

6. `queries/python/`
7. `queries/typescript/`
8. `queries/tsx/`
9. `queries/javascript/`
10. `queries/jsx/`

## 2. Contrato formal do adapter

Definir em `tree_sitter/types.py`:

```python
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

@dataclass(frozen=True, slots=True)
class QuerySet:
    language: str
    queries: Mapping[str, str]
    # Exemplo:
    # {
    #   "symbols": "queries/python/symbols.scm",
    #   "calls": "queries/python/calls.scm",
    #   "metadata": "queries/python/metadata.scm",
    # }

@dataclass(frozen=True, slots=True)
class SyntaxChunkSpec:
    startLine: int
    endLine: int
    content: str
    contentType: str
    chunkStrategy: str
    symbolName: str | None = None
    qualifiedSymbolName: str | None = None
    symbolType: str | None = None
    parentSymbol: str | None = None
    signature: str | None = None
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    callers: tuple[str, ...] = ()
    callees: tuple[str, ...] = ()
    coveredLineRanges: tuple[tuple[int, int], ...] = ()
    languageMetadata: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )

@runtime_checkable
class LanguageAdapter(Protocol):
    adapter_name: str
    supported_languages: tuple[str, ...]

    def query_set_for(self, language: str) -> QuerySet: ...
    def min_coverage_threshold(self, language: str) -> float: ...
    def chunk_source(
        self,
        *,
        text: str,
        language: str,
        file_content_type: str,
        class_max_lines: int,
    ) -> tuple[SyntaxChunkSpec, ...] | None: ...
```

### Regras do contrato

1. todo adapter suporta uma ou mais linguagens lógicas do indexer
2. todo adapter define `QuerySet` por linguagem
3. todo adapter define threshold de cobertura por linguagem
4. só `chunk.py` converte `SyntaxChunkSpec -> ChunkDocument`
5. `SyntaxChunkSpec` deve ser compatível com o protocolo usado por [chunk_graph.py](/apps/indexer/indexer/chunk_graph.py)
6. `languageMetadata` é exclusivamente interna

## 3. Uso de `languageMetadata`

### Uso permitido

1. logging de debug
2. troubleshooting
3. observabilidade interna
4. testes de adapter/query

### Uso proibido

1. não entra automaticamente em `ChunkDocument`
2. não entra no payload do Qdrant
3. não participa de `chunkId`
4. não pode ser usada para dependência funcional do MCP

### Requisito de implementação

Na conversão de `SyntaxChunkSpec -> ChunkDocument`, se `languageMetadata` existir, ela só pode ser registrada em log estruturado de debug.

## 4. Registry explícita e validada

Implementar em `registry.py` algo equivalente a:

```python
LANGUAGE_TO_ADAPTER = {
    "python": PythonTreeSitterAdapter(),
    "typescript": TypeScriptTreeSitterAdapter(),
    "typescriptreact": TypeScriptTreeSitterAdapter(),
    "javascript": TypeScriptTreeSitterAdapter(),
    "javascriptreact": TypeScriptTreeSitterAdapter(),
}
```

### Validação obrigatória da registry

Adicionar `_validate_registry()` chamado na inicialização do backend `tree_sitter`.

Validações:
1. todo valor implementa `LanguageAdapter`
2. toda chave está listada em `adapter.supported_languages`
3. não há linguagem sem adapter
4. `query_set_for(language)` funciona para toda linguagem suportada
5. todo `QuerySet` retornado contém ao menos `symbols`
6. todos os caminhos de query existem em disco

## 5. QuerySet multipropósito

### Decisão

`QuerySet` já nasce multipropósito.

### Grupos padronizados

1. `symbols`
2. `calls`
3. `metadata`

Se a linguagem não precisar de um grupo, o adapter pode omitir esse grupo.

### Benefício

Evita refactor futuro ao adicionar linguagens mais complexas.

## 6. Dispatch genérico em `chunk.py`

### Regra obrigatória

Eliminar conditionals específicos por linguagem em [chunk.py](/apps/indexer/indexer/chunk.py).

### Novo fluxo

1. classificar `content_type`
2. se for `doc_section`, `config_block` ou `sql_block`, usar chunkers atuais
3. se for coleção `code`, consultar `registry.get_adapter(language)`
4. se houver adapter:
   - chamar `adapter.chunk_source(...)`
   - validar cobertura
   - converter `SyntaxChunkSpec` em `ChunkDocument`
5. se não houver adapter ou se houver fallback, usar `line_window`

### Proibição

`chunk.py` não pode conhecer:
- `_should_use_python_symbol_chunking`
- `_should_use_ts_symbol_chunking`
- imports específicos de linguagem no fluxo principal

## 7. Convenção de `symbolType`

### Decisão

`symbolType` permanece string aberta e documentada por linguagem.

### Núcleo comum desta entrega

- `function`
- `method`
- `class`
- `component`
- `hook`
- `helper`

### Regra

Novos `symbolType` futuros são permitidos sem alterar schema público.

## Estratégia de Migração do Código Atual

### Congelar parsers atuais

Criar:
- `chunk_python_legacy.py`
- `chunk_ts_legacy.py`

### Wrappers públicos

- [chunk_python.py](/apps/indexer/indexer/chunk_python.py) vira wrapper de backend
- [chunk_ts.py](/apps/indexer/indexer/chunk_ts.py) vira wrapper de backend

### Seleção de backend

1. `CODE_CHUNK_PARSER_BACKEND=tree_sitter`
   - usa Tree-sitter
2. `CODE_CHUNK_PARSER_BACKEND=legacy`
   - usa parser congelado anterior
3. default final:
   - `tree_sitter`

## Estratégia de Migração dos Testes

### Decisão

Não reaproveitar os testes atuais de parser como se nada tivesse mudado.

### Mudanças

1. copiar os testes atuais específicos de parser para:
   - `test_chunk_python_legacy.py`
   - `test_chunk_ts_legacy.py`
2. adaptar [test_chunk_python.py](/apps/indexer/tests/test_chunk_python.py) para o adapter/wrapper novo
3. adaptar [test_chunk_ts.py](/apps/indexer/tests/test_chunk_ts.py) para o adapter/wrapper novo
4. manter testes de contrato nos wrappers públicos
5. legacy e tree-sitter devem coexistir durante o ciclo de estabilização

### Regra de aceite

Antes de remover o legacy no futuro:
1. testes do backend `legacy` continuam verdes
2. testes do backend `tree_sitter` continuam verdes
3. smoke do pipeline passa com os dois modos

## Fase 0 — Baseline e Benchmark Pré-Migração

### Objetivo

Criar baseline comparável antes da troca do parser.

### Entregas

1. benchmark do backend atual em:
   - fixture repo em [fixtures/chunking](/apps/indexer/tests/fixtures/chunking)
   - amostra do repo real
2. baseline de:
   - tempo de `indexer chunk`
   - tempo de `index`
   - quantidade de chunks por arquivo
   - distribuição de `chunkStrategy`
   - taxa de fallback
   - cobertura estrutural útil
3. benchmark por tamanho:
   - pequeno `<100 linhas`
   - médio `100-500`
   - grande `500-2000`
   - muito grande `5000+`
4. benchmark de carga:
   - 1000 arquivos sintéticos ou amostra equivalente de carga

### Calibração de thresholds

Para cada linguagem suportada:
1. medir cobertura estrutural útil em amostra conhecida
2. calcular P10 da cobertura
3. comparar com o threshold provisório definido abaixo
4. se a diferença for maior que `0.05`, ajustar a constante do adapter antes do rollout final

### Thresholds provisórios iniciais

- `python -> 0.70`
- `typescript -> 0.85`
- `typescriptreact -> 0.80`
- `javascript -> 0.80`
- `javascriptreact -> 0.75`

### Critério de saída

Ter números reais antes da implementação final e thresholds calibrados para o rollout.

## Fase 1 — Fundação Tree-sitter

### Arquivos

- [requirements.txt](/apps/indexer/requirements.txt)
- [config.py](/apps/indexer/indexer/config.py)
- `apps/indexer/indexer/tree_sitter/`

### Implementação

1. adicionar dependências fixadas
2. adicionar `CODE_CHUNK_PARSER_BACKEND`
3. implementar cache de:
   - `Language`
   - `Parser`
   - queries compiladas
4. implementar `LanguageAdapter`, `SyntaxChunkSpec` e `QuerySet`
5. implementar registry explícita
6. implementar `_validate_registry()`
7. validar grammars instaladas contra versions pinadas
8. implementar `debug_query_matches(...)` em `runtime.py`

### Testes

1. grammar loading por linguagem
2. version validation
3. registry validation
4. parser cache
5. query cache
6. helper de debug de query

## Fase 2 — Python com Tree-sitter

### Arquivos

- [chunk_python.py](/apps/indexer/indexer/chunk_python.py)
- `chunk_python_legacy.py`
- `tree_sitter/adapters/python.py`
- [chunk_graph.py](/apps/indexer/indexer/chunk_graph.py)

### Implementação

1. capturar:
   - `function_definition`
   - `decorated_definition`
   - `class_definition`
2. extrair:
   - funções
   - métodos
   - classes pequenas
   - classes grandes com resumo + métodos
3. incluir contexto lexical não coberto
4. extrair:
   - `symbolName`
   - `qualifiedSymbolName`
   - `symbolType`
   - `parentSymbol`
   - `signature`
5. grafo:
   - chamadas no subtree do símbolo
   - decorators entram em `callees`
   - manter proteções já conquistadas:
     - `get_client().load()` não vira símbolo local
     - `super.load()` não vira método da classe atual

### Fallback por adapter

Usar threshold calibrado na Fase 0, com default provisório `0.70`.

Volta para `line_window` se:
1. houver erro sintático relevante
2. houver nós missing/error em símbolo emitido
3. cobertura útil ficar abaixo do threshold do adapter

### Testes obrigatórios

1. função simples
2. `async def`
3. classe pequena
4. classe grande
5. decorators
6. comentários/contexto não coberto
7. `get_client().load()`
8. `super.load()`
9. arquivo inválido com fallback
10. golden tests estruturais de casos sensíveis

### Regressão estrutural

Os golden tests validam:
- `symbolName`
- `qualifiedSymbolName`
- `symbolType`
- `chunkStrategy`
- faixa de linhas com tolerância pequena quando o caso envolver decorator/whitespace

Regra:
- não usar snapshot textual bruto do conteúdo completo como gate principal

## Fase 3 — TypeScript / TSX / JS / JSX com Tree-sitter

### Arquivos

- [chunk_ts.py](/apps/indexer/indexer/chunk_ts.py)
- `chunk_ts_legacy.py`
- `tree_sitter/adapters/typescript.py`
- [chunk_graph.py](/apps/indexer/indexer/chunk_graph.py)

### Implementação

1. capturar:
   - `class_declaration`
   - `method_definition`
   - `function_declaration`
   - `lexical_declaration` com `arrow_function` ou `function`
   - `export default` nomeado e anônimo
   - getters e setters
2. classificar:
   - `hook`
   - `component`
   - `helper`
3. tratar casos obrigatórios:
   - overloads
   - decorators de classe e método
   - decorators multiline
   - `export default memo(function Name() {})`
   - `export default forwardRef(function Name() {})`
   - `export default memo(forwardRef(function Name() {}))`
   - `export default () => ...`
   - `export default async () => ...`
   - `export default function() {}`
   - `export default class extends Base {}`
   - `abstract class`
   - fragments JSX
   - JSX condicional e aninhado

4. regra para wrappers compostos:
   - capturar primeiro a função/componente mais interna
   - descartar `memo`, `forwardRef` e wrappers equivalentes como candidatos a `symbolName`
   - se não for possível extrair nome confiável, usar `default`
   - nunca emitir `memo` ou `forwardRef` como `symbolName`

5. grafo:
   - chamadas só no subtree do símbolo
   - incluir decorators
   - manter correções existentes:
     - `new Client().run()` não vira símbolo local
     - `super.load()` não vira método da classe atual

### Compatibilidade de decorators

Documentar e testar:
1. decorators legacy
2. decorators Stage-3 suportados pela grammar usada
3. explicitar no README qual variante está suportada na entrega

### Fallback por adapter

Usar thresholds calibrados na Fase 0, com defaults provisórios:
- `typescript -> 0.85`
- `typescriptreact -> 0.80`
- `javascript -> 0.80`
- `javascriptreact -> 0.75`

### Testes obrigatórios

1. helper
2. hook
3. component
4. classe pequena
5. classe grande
6. overloads
7. getters/setters
8. default export nomeado
9. default export anônimo
10. wrappers `memo` / `forwardRef`
11. wrappers compostos `memo(forwardRef(...))`
12. decorators multiline
13. JSX fragment
14. JSX condicional aninhado
15. arquivo inválido com fallback
16. golden tests estruturais dos casos críticos acima

## Fase 4 — Integração no Pipeline

### Arquivos

- [chunk.py](/apps/indexer/indexer/chunk.py)
- [__main__.py](/apps/indexer/indexer/__main__.py)

### Implementação

1. [chunk.py](/apps/indexer/indexer/chunk.py) passa a usar dispatch genérico via registry
2. `docs`, `config` e `sql` permanecem como estão
3. manter:
   - `ChunkDocument`
   - `summaryText`
   - `contextText`
   - `chunkId`
   - `contentHash`
4. warnings estruturados por arquivo em caso de fallback
5. nenhum conditional por linguagem no fluxo principal

## Fase 5 — Schema, Operação e Observabilidade

### Schema

1. subir `CHUNK_SCHEMA_VERSION` para `v6`
2. manter bloqueio explícito de mistura `v5/v6`
3. rebuild completo obrigatório

### Observabilidade

Adicionar log estruturado por arquivo com shape mínimo:

```json
{
  "event": "chunk_parse",
  "parser_backend": "tree_sitter",
  "adapter": "typescript",
  "language": "typescriptreact",
  "queries": ["symbols", "calls", "metadata"],
  "fallback": false,
  "fallback_reason": null,
  "chunk_count": 4,
  "coverage": 0.92,
  "duration_ms": 12
}
```

### Métricas mínimas

1. arquivos parseados por backend
2. taxa de fallback por linguagem e adapter
3. duração média e p95 por linguagem
4. chunks gerados por linguagem
5. erros de grammar loading
6. cobertura estrutural média por linguagem

### Regra explícita

Fallback não entra no payload do Qdrant.

## Fase 6 — Escalabilidade para Novas Linguagens

### Objetivo

Garantir que a terceira linguagem seja barata de adicionar.

### Entregas

1. template oficial de adapter em `tree_sitter/adapters/_template.py`
2. guia `docs/tree-sitter/adding-language.md`
3. teste de contrato para adapters
4. checklist de inclusão de nova linguagem
5. documentação de `languageMetadata`
6. documentação de `QuerySet` multipropósito

### Checklist oficial de nova linguagem

1. adicionar grammar dependency fixada
2. criar adapter implementando `LanguageAdapter`
3. definir `QuerySet`
4. registrar em `registry.py`
5. definir `min_coverage_threshold`
6. criar fixtures
7. adicionar testes unitários e de integração
8. adicionar golden tests estruturais
9. validar benchmark e smoke

### Regra de escalabilidade

Adicionar nova linguagem futura não pode exigir modificação em [chunk.py](/apps/indexer/indexer/chunk.py).

## Fase 7 — Validação Final, MCP e Gate de Qualidade

### Comparação obrigatória `legacy vs tree_sitter`

Comparar:
1. tempo de `indexer chunk`
2. tempo de `index`
3. número de chunks por arquivo
4. distribuição de `chunkStrategy`
5. taxa de fallback
6. preservação dos campos do payload

### Validação MCP

Adicionar validação de retrieval com o MCP sobre índice gerado por Tree-sitter.

Regras:
1. indexar coleção temporária com backend `tree_sitter`
2. executar consultas reais via MCP/serviço de busca
3. comparar com backend `legacy` pelo menos:
   - shape dos resultados
   - presença de evidências relevantes
   - não degradação clara de retrieval
4. não exigir igualdade de ranking exata nem igualdade literal de resposta natural

### Gate de qualidade

1. 100% dos campos de payload preservados
2. smoke `index -> search` aprovado
3. validação MCP aprovada
4. taxa de fallback em repos conhecidos abaixo do threshold documentado
5. parsing Tree-sitter não pode degradar severamente sem explicação documentada

### Meta inicial de performance

Meta inicial:
- Tree-sitter até `2x` do legacy em parsing puro nos cenários conhecidos
- benchmark de carga de 1000 arquivos não pode ultrapassar `3x` o tempo do legacy sem investigação formal

## Estratégia de Fixtures

### Base principal

Usar:
- [fixtures/chunking](/apps/indexer/tests/fixtures/chunking)

### Expandir com fixtures novas

Adicionar:
1. `src/complex-component.tsx`
   - `memo + forwardRef`
   - component default export
   - hook/helper internos
2. `src/overloads.ts`
3. `src/stage3-decorators.ts`
4. `src/legacy-decorators.ts`
5. `src/very-large-module.ts`
6. `src/very-large-module.py`

## Estratégia de Regressão

### Comparação

Não usar diff textual bruto como verdade única.

Usar:
1. invariantes obrigatórios
2. regressão estrutural
3. golden tests aprovados
4. revisão manual só de divergências relevantes

## Testes e Cenários

### Testes unitários

Arquivos:
- [test_chunk_python.py](/apps/indexer/tests/test_chunk_python.py)
- [test_chunk_ts.py](/apps/indexer/tests/test_chunk_ts.py)
- [test_chunk.py](/apps/indexer/tests/test_chunk.py)
- [test_config.py](/apps/indexer/tests/test_config.py)
- `test_chunk_python_legacy.py`
- `test_chunk_ts_legacy.py`

Cobertura mínima:
1. grammar loading
2. version validation
3. adapter contract
4. registry validation
5. query loading
6. query debug helper
7. parsing por linguagem
8. fallback por parse error e coverage
9. `chunkId` estável
10. `contentHash` mutável
11. `summaryText` e `contextText`
12. `callers` e `callees`
13. edge cases historicamente sensíveis
14. golden tests estruturais

### Testes de integração

Arquivos:
- [test_cli.py](/apps/indexer/tests/test_cli.py)
- smoke do indexer
- testes MCP relevantes

Cobertura mínima:
1. `indexer chunk` com backend default
2. `indexer chunk` com backend `legacy`
3. `indexer index` em collection temporária
4. `indexer search` após indexação
5. bloqueio de mistura `v5/v6`
6. validação MCP

## Runbook Operacional

### Rollout

1. backup lógico do estado atual
2. atualizar dependências do indexer
3. validar grammars e versions
4. recriar ou limpar collections antigas
5. rodar rebuild completo
6. rodar smoke `index -> search`
7. validar fallback, coverage, cardinalidade, tempo e MCP
8. liberar `tree_sitter` como backend default

### Sequência documentada

1. `make py-setup`
2. validar ambiente do indexer
3. `make health`
4. rebuild completo do índice
5. smoke controlado de busca
6. validar logs estruturados de parsing

### Rollback

1. setar `CODE_CHUNK_PARSER_BACKEND=legacy`
2. recriar/reindexar conforme backend selecionado
3. repetir smoke `index -> search`
4. usar rollback apenas como estabilização temporária

### Remoção do legacy

Follow-up separado.

Critério:
1. 2 sprints de estabilização
2. zero incidente crítico de parsing
3. taxa de fallback controlada
4. smoke, benchmark e validação MCP estáveis

## Critérios de Aceitação Finais

1. `tree_sitter` é o backend default para código.
2. `legacy` permanece disponível temporariamente.
3. `chunk.py` não conhece linguagens específicas.
4. registry explícita resolve adapters e é validada na inicialização.
5. `LanguageAdapter`, `SyntaxChunkSpec` e `QuerySet` estão formalizados.
6. Python e TS/TSX/JS/JSX continuam emitindo payload compatível.
7. `index -> search` funciona ponta a ponta.
8. a validação MCP não mostra degradação evidente de retrieval.
9. existem métricas e logs suficientes para diagnosticar fallback e degradação.
10. benchmark antes/depois está documentado.
11. adicionar nova linguagem não exige mexer em [chunk.py](/apps/indexer/indexer/chunk.py).

## Assunções e Defaults

1. a primeira entrega Tree-sitter cobre apenas linguagens de código já presentes no repositório
2. `docs`, `config` e `sql` continuam fora desta migração
3. `symbolType` permanece string aberta e documentada
4. `languageMetadata` é interna e não entra automaticamente no payload
5. registry explícita é preferida a auto-discovery nesta primeira versão
6. thresholds de cobertura são calibrados na Fase 0, com defaults provisórios já definidos
7. a troca de parser é mudança estrutural suficiente para exigir `v6`

## Arquivos-Alvo

1. [apps/indexer/requirements.txt](/apps/indexer/requirements.txt)
2. [apps/indexer/indexer/config.py](/apps/indexer/indexer/config.py)
3. [apps/indexer/indexer/chunk.py](/apps/indexer/indexer/chunk.py)
4. [apps/indexer/indexer/chunk_python.py](/apps/indexer/indexer/chunk_python.py)
5. [apps/indexer/indexer/chunk_ts.py](/apps/indexer/indexer/chunk_ts.py)
6. [apps/indexer/indexer/chunk_graph.py](/apps/indexer/indexer/chunk_graph.py)
7. [apps/indexer/indexer/chunk_models.py](/apps/indexer/indexer/chunk_models.py)
8. [apps/indexer/indexer/__main__.py](/apps/indexer/indexer/__main__.py)
9. `apps/indexer/indexer/tree_sitter/`
10. `apps/indexer/indexer/chunk_python_legacy.py`
11. `apps/indexer/indexer/chunk_ts_legacy.py`
12. [apps/indexer/tests/test_chunk_python.py](/apps/indexer/tests/test_chunk_python.py)
13. [apps/indexer/tests/test_chunk_ts.py](/apps/indexer/tests/test_chunk_ts.py)
14. [apps/indexer/tests/test_chunk.py](/apps/indexer/tests/test_chunk.py)
15. [apps/indexer/tests/test_cli.py](/apps/indexer/tests/test_cli.py)
16. [apps/indexer/tests/test_config.py](/apps/indexer/tests/test_config.py)
17. `apps/indexer/tests/test_chunk_python_legacy.py`
18. `apps/indexer/tests/test_chunk_ts_legacy.py`
19. [apps/indexer/tests/fixtures/chunking](/apps/indexer/tests/fixtures/chunking)
20. [apps/indexer/README.md](/apps/indexer/README.md)
21. [docs/OPERATIONS.md](/docs/OPERATIONS.md)
22. [docs/ROADMAP.md](/docs/ROADMAP.md)
23. [docs/tree-sitter/plan.md](/docs/tree-sitter/plan.md)
24. [docs/tree-sitter/adding-language.md](/docs/tree-sitter/adding-language.md)
