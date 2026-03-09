# Plano Completo de Integração do Tree-sitter no Code Compass

## Resumo

Este plano substitui a base atual de parsing semântico de código por
Tree-sitter, preservando o fluxo `scan -> chunk -> embed -> upsert -> search`,
mantendo o payload e preparando a arquitetura para crescer além de
Python e TypeScript.

Decisões fechadas:

1. rollout direto: `tree_sitter` será o backend default
2. primeira entrega funcional cobre as linguagens já presentes no repositório:
   - `python`
   - `typescript`
   - `typescriptreact`
   - `javascript`
   - `javascriptreact`
3. `docs`, `config` e `sql` continuam com seus chunkers especializados atuais
4. o índice sobe de `v5` para `v6`, com rebuild completo obrigatório
5. o backend `legacy` será mantido temporariamente como escape hatch operacional
6. a arquitetura deve escalar sem exigir novos conditionals em `chunk.py`
7. a escalabilidade será feita com:
   - `LanguageAdapter` formal
   - `SyntaxChunkSpec` formal
   - registry explícita e tipada
   - dispatch genérico em `chunk.py`
   - thresholds e query sets por adapter

## Objetivo

Trocar o parsing atual por Tree-sitter para:

1. reduzir fragilidade heurística, especialmente em `TS/TSX/JS`
2. unificar a base de parsing semântico de código
3. preparar expansão futura para outras linguagens
4. preservar o contrato de chunking já consumido por indexação, busca e MCP
5. tornar a adição da terceira linguagem barata e previsível

## Fora de Escopo

1. migrar `markdown`, `config` ou `sql` para Tree-sitter neste ciclo
2. entregar suporte semântico completo a Go, Rust ou Java nesta primeira implementação
3. mudar o contrato público do MCP
4. redesenhar o payload do Qdrant além do necessário para schema `v6`
5. remover o backend `legacy` neste mesmo trabalho

## Estado Atual

Hoje o indexer usa:

1. `ast` nativo em [chunk_python.py](../../apps/indexer/indexer/chunk_python.py)
2. parser heurístico com regex e balanceamento estrutural em [chunk_ts.py](../../apps/indexer/indexer/chunk_ts.py)
3. dispatch manual por linguagem em [chunk.py](../../apps/indexer/indexer/chunk.py)
4. schema atual `v5` em [chunk_models.py](../../apps/indexer/indexer/chunk_models.py)

Problemas atuais:

1. manutenção alta do parser heurístico
2. acoplamento do dispatch a linguagens específicas
3. pouca previsibilidade para adicionar novas linguagens
4. baixa observabilidade sobre fallback, cobertura e custo do parsing
5. falta de protocolo formal para adapters

## Mudanças de Interface e Contrato

### Mudanças explícitas

1. adicionar `CODE_CHUNK_PARSER_BACKEND=tree_sitter|legacy` em
   [config.py](../../apps/indexer/indexer/config.py), padrão `tree_sitter`
2. subir `CHUNK_SCHEMA_VERSION` de `v5` para `v6` em [chunk_models.py](../../apps/indexer/indexer/chunk_models.py)
3. adicionar logs estruturados de parsing e fallback no runtime do indexer
4. documentar rebuild completo obrigatório e rollback operacional

### Mudanças que não serão feitas

1. não renomear estratégias já públicas:
   - `python_symbol`
   - `ts_symbol`
   - `line_window`
2. não remover campos atuais do payload
3. não adicionar estado de fallback ao payload do Qdrant
4. não mudar a forma como `ChunkDocument` é serializado externamente

## Estratégia de Dependências e Compatibilidade

### Dependências novas

Adicionar em [requirements.txt](../../apps/indexer/requirements.txt):

1. binding principal de Tree-sitter
2. grammar package Python
3. grammar package TypeScript
4. grammar package JavaScript, se separado

### Regra de versionamento

1. fixar versões exatas dos bindings e grammars na primeira entrega
2. documentar matriz de compatibilidade mínima em [apps/indexer/README.md](../../apps/indexer/README.md)
3. não permitir upgrades implícitos amplos neste ciclo
4. qualquer upgrade futuro exige benchmark + regressão de fixtures

### Matriz mínima documentada

Documentar:

1. versão do binding Tree-sitter Python
2. versão das grammars Python/TypeScript/JavaScript
3. linguagens suportadas semanticamente nesta entrega
4. linguagens que continuam no parser atual ou no fallback linear

## Arquitetura Proposta

## 1. Pacote interno `tree_sitter/`

Criar `apps/indexer/indexer/tree_sitter/` com:

1. `runtime.py`
   - carrega grammars
   - instancia `Language`
   - instancia e reutiliza `Parser`
   - compila e reutiliza `Query`
   - expõe helpers de range, bytes e texto

2. `types.py`
   - define `SyntaxChunkSpec`
   - define `LanguageAdapter`
   - define `QuerySet`

3. `registry.py`
   - mantém mapeamento explícito de linguagens para adapters
   - não usa auto-discovery

4. `adapters/python.py`
   - adapter Tree-sitter para Python

5. `adapters/typescript.py`
   - adapter Tree-sitter para `typescript`, `typescriptreact`, `javascript`, `javascriptreact`

6. `queries/python.scm`
7. `queries/typescript.scm`
8. `queries/tsx.scm`
9. `queries/javascript.scm`
10. `queries/jsx.scm`

## 2. Contrato formal do adapter

Definir em `tree_sitter/types.py`:

```python
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Protocol

@dataclass(frozen=True, slots=True)
class QuerySet:
    language: str
    query_file: str

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

1. todo adapter deve suportar uma ou mais linguagens lógicas do indexer
2. todo adapter deve resolver seu próprio `QuerySet`
3. todo adapter deve expor threshold mínimo de cobertura por linguagem
4. só `chunk.py` converte `SyntaxChunkSpec -> ChunkDocument`
5. `languageMetadata` é opcional e não entra automaticamente no payload externo

## 3. Registry explícita e tipada

Implementar em `registry.py`:

```python
LANGUAGE_TO_ADAPTER = {
    "python": PythonTreeSitterAdapter(),
    "typescript": TypeScriptTreeSitterAdapter(),
    "typescriptreact": TypeScriptTreeSitterAdapter(),
    "javascript": TypeScriptTreeSitterAdapter(),
    "javascriptreact": TypeScriptTreeSitterAdapter(),
}
```

### Regras

1. registry explícita, sem auto-discovery nesta primeira versão
2. nenhuma nova linguagem exigirá mudança em `chunk.py`
3. adicionar nova linguagem exigirá:
   - grammar dependency
   - adapter novo ou ampliação de adapter existente
   - mapeamento em `registry.py`
   - query set correspondente
   - testes e fixtures

## 4. Dispatch genérico em `chunk.py`

### Regra obrigatória

Eliminar conditionals específicos por linguagem em [chunk.py](../../apps/indexer/indexer/chunk.py).

### Novo fluxo

1. classificar `content_type`
2. se for `doc_section`, `config_block` ou `sql_block`, manter os chunkers atuais
3. se for coleção `code`, consultar `registry.get_adapter(language)`
4. se houver adapter:
   - chamar `adapter.chunk_source(...)`
   - converter `SyntaxChunkSpec` em `ChunkDocument`
5. se não houver adapter ou houver fallback, usar `line_window`

### Proibição

Não deixar `chunk.py` conhecer:

- `_should_use_python_symbol_chunking()`
- `_should_use_ts_symbol_chunking()`
- imports específicos de linguagem no fluxo principal

## 5. Query resolution por linguagem

A decisão de query file não fica no registry; fica no adapter.

### Exemplo

No adapter TypeScript:

- `typescript` -> `typescript.scm`
- `typescriptreact` -> `tsx.scm`
- `javascript` -> `javascript.scm`
- `javascriptreact` -> `jsx.scm`

No adapter Python:

- `python` -> `python.scm`

### Regra

A registry escolhe o adapter. O adapter escolhe a query e a grammar correta.

## 6. Convenção de `symbolType`

### Regra escolhida

`s`ymbolType continua sendo string aberta e documentada, sem enum rígido global.

### Núcleo comum

Valores comuns desta entrega:

- `function`
- `method`
- `class`
- `component`
- `hook`
- `helper`

### Extensibilidade futura

Permitir valores novos por linguagem futura, por exemplo:

- Rust: `trait`, `impl`, `mod`
- Go: `interface`, `struct`, `receiver_method`

### Regra de payload

O payload já suporta string livre, não haverá bloqueio por schema para valores
novos de `symbolType`.

## Estratégia de Migração do Código Atual

### Congelar parsers atuais

Criar:

- `chunk_python_legacy.py`
- `chunk_ts_legacy.py`

Esses módulos recebem a implementação atual sem mudança funcional.

### Wrappers públicos

- [chunk_python.py](../../apps/indexer/indexer/chunk_python.py) vira wrapper
- [chunk_ts.py](../../apps/indexer/indexer/chunk_ts.py) vira wrapper de backend

### Seleção de backend

1. `CODE_CHUNK_PARSER_BACKEND=tree_sitter`
   - usa Tree-sitter
2. `CODE_CHUNK_PARSER_BACKEND=legacy`
   - usa parser congelado anterior
3. default:
   - `tree_sitter`

## Fase 0 — Baseline e Benchmark Pré-Migração

### Objetivo da Fase 0

Criar baseline comparável antes da troca do parser.

### Entregas do Baseline

1. benchmark do backend atual em:
   - fixture repo em [fixtures/chunking](../../apps/indexer/tests/fixtures/chunking)
   - amostra do repo real
2. salvar baseline de:
   - tempo de `indexer chunk`
   - tempo de `index`
   - quantidade de chunks por arquivo
   - distribuição de `chunkStrategy`
   - taxa de fallback
   - cobertura estrutural útil
3. registrar baseline em documentação técnica em `docs/tree-sitter/`

### Critério de saída

Ter números reais antes de implementar Tree-sitter.

## Fase 1 — Fundação Tree-sitter

### Arquivos da Fase 1

- [requirements.txt](../../apps/indexer/requirements.txt)
- [config.py](../../apps/indexer/indexer/config.py)
- `apps/indexer/indexer/tree_sitter/`

### Implementação da Fase 1

1. adicionar dependências fixadas
2. adicionar `CODE_CHUNK_PARSER_BACKEND`
3. implementar cache de:
   - `Language`
   - `Parser`
   - `Query`
4. implementar `LanguageAdapter`, `SyntaxChunkSpec` e `QuerySet`
5. implementar registry explícita
6. falhar cedo se backend for `tree_sitter` e grammar não carregar

### Testes

1. load de grammar por linguagem
2. cache de parser
3. cache de query
4. contrato do adapter
5. registry resolvendo adapter por linguagem

## Fase 2 — Python com Tree-sitter

### Arquivos da Fase 2

- [chunk_python.py](../../apps/indexer/indexer/chunk_python.py)
- `chunk_python_legacy.py`
- `tree_sitter/adapters/python.py`
- [chunk_graph.py](../../apps/indexer/indexer/chunk_graph.py)

### Implementação da Fase 2

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
   - preservar correções já existentes:
     - `get_client().load()` não vira símbolo local
     - `super.load()` não vira método da classe atual

### Fallback do Python Adapter

Python define seu próprio threshold:

- `min_coverage_threshold("python") -> 0.70`

Volta para `line_window` se:

1. houver erro sintático relevante
2. houver nós missing/error em símbolo emitido
3. cobertura útil ficar abaixo do threshold do adapter

### Testes obrigatórios Python

1. função simples
2. `async def`
3. classe pequena
4. classe grande
5. decorators
6. comentários/contexto não coberto
7. `get_client().load()`
8. `super.load()`
9. arquivo inválido com fallback

## Fase 3 — TypeScript / TSX / JS / JSX com Tree-sitter

### Arquivos da Fase 3

- [chunk_ts.py](../../apps/indexer/indexer/chunk_ts.py)
- `chunk_ts_legacy.py`
- `tree_sitter/adapters/typescript.py`
- [chunk_graph.py](../../apps/indexer/indexer/chunk_graph.py)

### Implementação da Fase 3

1. capturar:
   - `class_declaration`
   - `method_definition`
   - `function_declaration`
   - `lexical_declaration` com `arrow_function` ou `function`
   - `export default` nomeado e anônimo
   - getters e setters
2. classificar semântica:
   - `hook`
   - `component`
   - `helper`
3. tratar casos obrigatórios:
   - overloads
   - decorators de classe e método
   - decorators multiline
   - `export default memo(function Name() {})`
   - `export default forwardRef(function Name() {})`
   - `export default () => ...`
   - `export default async () => ...`
   - `export default function() {}`
   - `export default class extends Base {}`
   - `abstract class`
   - fragments JSX
   - JSX condicional e aninhado
4. grafo:
   - chamadas só no subtree do símbolo
   - incluir decorators
   - preservar correções já conquistadas:
     - `new Client().run()` não vira símbolo local
     - `super.load()` não vira método da classe atual

### Compatibilidade de decorators

Documentar e testar:

1. decorators legacy
2. decorators Stage-3 suportados pela grammar usada
3. explicitar no README qual variante é suportada nesta entrega

### Fallback do TS Adapter

TypeScript adapter define:

- `typescript` / `javascript` (e extensões com react) -> threshold `0.80`

### Testes obrigatórios TS

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
11. decorators multiline
12. JSX fragment
13. JSX condicional aninhado
14. arquivo inválido com fallback

## Fase 4 — Integração do Pipeline

### Arquivos da Fase 4

- [chunk.py](../../apps/indexer/indexer/chunk.py)
- [__main__.py](../../apps/indexer/indexer/__main__.py)

### Implementação da Fase 4

1. [chunk.py](../../apps/indexer/indexer/chunk.py) usa registry genérico
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
  "query_file": "tsx.scm",
  "fallback": false,
  "fallback_reason": null,
  "chunk_count": 4,
  "coverage": 0.92,
  "duration_ms": 12
}
```

Em fallback:

```json
{
  "event": "chunk_parse",
  "parser_backend": "tree_sitter",
  "adapter": "python",
  "language": "python",
  "query_file": "python.scm",
  "fallback": true,
  "fallback_reason": "coverage_below_threshold",
  "chunk_count": 1,
  "coverage": 0.48,
  "duration_ms": 3
}
```

### Métricas mínimas

1. arquivos parseados por backend
2. taxa de fallback por linguagem e por adapter
3. duração média e p95 por linguagem
4. chunks gerados por linguagem
5. erros de grammar loading
6. cobertura estrutural média por linguagem

### Regra explícita

Fallback não entra no payload do Qdrant.

## Fase 6 — Escalabilidade para Novas Linguagens

### Objetivo de Escalabilidade

Garantir que a terceira linguagem seja fácil de adicionar, não só a segunda.

### Entregas de Escalabilidade

1. template oficial de adapter em `tree_sitter/adapters/_template.py`
2. guia de adição de linguagem em `docs/tree-sitter/`
3. teste de contrato para adapters
4. documentação de query set por linguagem
5. checklist de inclusão de nova linguagem

### Checklist de nova linguagem

Para adicionar uma linguagem futura:

1. adicionar grammar dependency fixada
2. criar adapter implementando `LanguageAdapter`
3. definir query file(s)
4. registrar linguagem em `registry.py`
5. definir threshold de cobertura por adapter
6. adicionar fixtures
7. adicionar testes unitários e de integração
8. validar benchmark e smoke

### Regra de escalabilidade

A inclusão de nova linguagem futura não pode exigir mudança em [chunk.py](../../apps/indexer/indexer/chunk.py).

## Fase 7 — Benchmark Pós-Migração e Gate de Qualidade

### Comparação obrigatória

Comparar `legacy` vs `tree_sitter` em:

1. tempo de `indexer chunk`
2. tempo de `index`
3. número de chunks por arquivo
4. distribuição de `chunkStrategy`
5. taxa de fallback
6. preservação dos campos do payload

### Gate de qualidade

1. 100% dos campos de payload preservados
2. smoke `index -> search` aprovado
3. taxa de fallback em repos conhecidos abaixo do threshold documentado
4. parsing `tree_sitter` não pode degradar sem explicação documentada

Meta inicial:

- custo de parsing Tree-sitter até `1.5x` do legacy em cenários conhecidos

Isso é meta de engenharia, não contrato público.

## Estratégia de Regressão

### Base principal de fixtures

Usar:

- [fixtures/chunking](../../apps/indexer/tests/fixtures/chunking)

Expandir com:

1. Python com decorators complexos
2. TS com overloads
3. TSX com wrappers
4. TSX com JSX fragment e JSX aninhado
5. default exports anônimos
6. decorators Stage-3 e legacy
7. arquivos inválidos para fallback

### Estratégia de comparação

Não usar diff textual cego como verdade absoluta.

Usar:

1. invariantes obrigatórios
2. regressão estrutural
3. revisão manual só para divergências relevantes

## Testes e Cenários

### Testes unitários

Arquivos:

- [test_chunk_python.py](../../apps/indexer/tests/test_chunk_python.py)
- [test_chunk_ts.py](../../apps/indexer/tests/test_chunk_ts.py)
- [test_chunk.py](../../apps/indexer/tests/test_chunk.py)
- [test_config.py](../../apps/indexer/tests/test_config.py)

Cobertura mínima:

1. grammar loading
2. query loading
3. adapter contract
4. registry resolution
5. parsing por linguagem
6. fallback por parse error e coverage
7. `chunkId` estável
8. `contentHash` mutável
9. `summaryText` e `contextText`
10. `callers` e `callees`
11. casos de borda já corrigidos historicamente

### Testes de integração

Arquivos:

- [test_cli.py](../../apps/indexer/tests/test_cli.py)
- smoke do indexer

Cobertura mínima:

1. `indexer chunk` com backend default
2. `indexer chunk` com backend `legacy`
3. `indexer index` em collection temporária
4. `indexer search` após indexação
5. bloqueio de mistura `v5/v6`

## Runbook Operacional

### Rollout

1. backup lógico do estado atual
2. atualizar dependências do indexer
3. validar grammar loading
4. recriar ou limpar collections antigas
5. rodar rebuild completo
6. rodar smoke `index -> search`
7. validar taxa de fallback, cobertura e cardinalidade
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
4. usar rollback só como estabilização temporária

### Remoção do legacy

Follow-up separado.

Critério:

1. 2 sprints de estabilização
2. zero incidente crítico de parsing
3. taxa de fallback controlada
4. smoke e benchmark estáveis

## Critérios de Aceitação Finais

1. `tree_sitter` é o backend default para código
2. `legacy` continua disponível temporariamente
3. `chunk.py` não conhece linguagens específicas
4. `registry.py` resolve adapters explicitamente
5. `LanguageAdapter` e `SyntaxChunkSpec` estão formalizados
6. Python e TS/TSX/JS/JSX continuam emitindo payload compatível
7. `index -> search` funciona ponta a ponta
8. existem métricas e logs suficientes para fallback e degradação
9. benchmark antes/depois está documentado
10. não pode exigir modificações em [chunk.py](../../apps/indexer/indexer/chunk.py)

## Assunções e Defaults

1. a primeira entrega semanticamente suportada foca nas linguagens já
   presentes no repositório
2. `docs`, `config` e `sql` continuam fora desta migração
3. `symbolType` permanece string aberta e documentada
4. `languageMetadata` é interna e não entra automaticamente no payload
5. registry explícita é preferida a auto-discovery nesta primeira versão
6. thresholds de cobertura são por adapter, não globais
7. a troca de parser é mudança estrutural suficiente para exigir `v6`

## Arquivos-Alvo

1. [apps/indexer/requirements.txt](../../apps/indexer/requirements.txt)
2. [apps/indexer/indexer/config.py](../../apps/indexer/indexer/config.py)
3. [apps/indexer/indexer/chunk.py](../../apps/indexer/indexer/chunk.py)
4. [apps/indexer/indexer/chunk_python.py](../../apps/indexer/indexer/chunk_python.py)
5. [apps/indexer/indexer/chunk_ts.py](../../apps/indexer/indexer/chunk_ts.py)
6. [apps/indexer/indexer/chunk_graph.py](../../apps/indexer/indexer/chunk_graph.py)
7. [apps/indexer/indexer/chunk_models.py](../../apps/indexer/indexer/chunk_models.py)
8. [apps/indexer/indexer/__main__.py](../../apps/indexer/indexer/__main__.py)
9. `apps/indexer/indexer/tree_sitter/`
10. `apps/indexer/indexer/chunk_python_legacy.py`
11. `apps/indexer/indexer/chunk_ts_legacy.py`
12. [apps/indexer/tests/test_chunk_python.py](../../apps/indexer/tests/test_chunk_python.py)
13. [apps/indexer/tests/test_chunk_ts.py](../../apps/indexer/tests/test_chunk_ts.py)
14. [apps/indexer/tests/test_chunk.py](../../apps/indexer/tests/test_chunk.py)
15. [apps/indexer/tests/test_cli.py](../../apps/indexer/tests/test_cli.py)
16. [apps/indexer/tests/test_config.py](../../apps/indexer/tests/test_config.py)
17. [apps/indexer/tests/fixtures/chunking](../../apps/indexer/tests/fixtures/chunking)
18. [apps/indexer/README.md](../../apps/indexer/README.md)
19. [docs/OPERATIONS.md](../../docs/OPERATIONS.md)
20. [docs/ROADMAP.md](../../docs/ROADMAP.md)
21. [docs/tree-sitter/plan.md](../../docs/tree-sitter/plan.md)
