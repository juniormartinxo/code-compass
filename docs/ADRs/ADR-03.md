## ADR-003 — “Evidence-first” como regra do produto

**Status:** Aceito  
**Data:** 2026-02-08

### Contexto
Agentes de IA podem “alucinar” quando o contexto é fraco ou ambíguo. Em ambiente corporativo, confiança é requisito: o usuário precisa ver **de onde veio** a resposta.

### Decisão
Toda tool de recuperação deve retornar **evidência auditável**:
- `path`
- `startLine` / `endLine`
- `snippet` (ou referência para o trecho)
- `score` (ranking)

Se não houver evidência suficiente, o sistema deve preferir retornar “não encontrado/baixa confiança” em vez de inventar.

### Consequências
**Positivas**
- Aumenta confiança e adoção interna.
- Facilita code review e validação humana.
- Reduz risco de decisões erradas baseadas em resposta inventada.

**Negativas**
- Requer disciplina no chunking e no retorno das tools.
- Pode “parecer” menos mágico (mas é mais correto).