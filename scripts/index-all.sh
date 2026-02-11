#!/usr/bin/env bash
# ============================================================
# index-all.sh — Indexa todos os repositórios em code-base/
#
# Uso:
#   ./scripts/index-all.sh                   # indexa todos
#   ./scripts/index-all.sh repo-a repo-b     # indexa apenas os listados
#
# Requisitos:
#   - Qdrant rodando (QDRANT_URL)
#   - Ollama rodando (OLLAMA_URL)
#   - venv do indexer criado (apps/indexer/.venv)
# ============================================================
set -euo pipefail

# ── Diretório raiz do monorepo ──────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CODE_BASE_DIR="$PROJECT_ROOT/code-base"
INDEXER_DIR="$PROJECT_ROOT/apps/indexer"

# ── Carregar variáveis de ambiente ──────────────────────────
if [[ -f "$PROJECT_ROOT/.env.local" ]]; then
  echo "📦 Carregando .env.local..."
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env.local"
  set +a
fi

# ── Ativar venv do indexer (se existir) ─────────────────────
if [[ -f "$INDEXER_DIR/.venv/bin/activate" ]]; then
  echo "🐍 Ativando venv do indexer..."
  # shellcheck disable=SC1091
  source "$INDEXER_DIR/.venv/bin/activate"
fi

# ── Validações ──────────────────────────────────────────────
if [[ ! -d "$CODE_BASE_DIR" ]]; then
  echo "❌ Diretório code-base/ não encontrado em: $CODE_BASE_DIR"
  exit 1
fi

# ── Listar repositórios a indexar ───────────────────────────
if [[ $# -gt 0 ]]; then
  # Repos passados como argumento
  REPOS=("$@")
else
  # Todos os subdiretórios de code-base/
  REPOS=()
  for dir in "$CODE_BASE_DIR"/*/; do
    [[ -d "$dir" ]] || continue
    REPOS+=("$(basename "$dir")")
  done
fi

if [[ ${#REPOS[@]} -eq 0 ]]; then
  echo "⚠️  Nenhum repositório encontrado em code-base/"
  exit 0
fi

echo ""
echo "🔍 Repositórios para indexar: ${REPOS[*]}"
echo "────────────────────────────────────────────"
echo ""

# ── Contadores ──────────────────────────────────────────────
TOTAL=${#REPOS[@]}
SUCCESS=0
FAILED=0
FAILED_REPOS=()

# ── Loop de indexação ───────────────────────────────────────
for repo_name in "${REPOS[@]}"; do
  REPO_PATH="$CODE_BASE_DIR/$repo_name"

  if [[ ! -d "$REPO_PATH" ]]; then
    echo "⚠️  Pulando '$repo_name': diretório não encontrado"
    FAILED=$((FAILED + 1))
    FAILED_REPOS+=("$repo_name")
    continue
  fi

  echo "▶ [$((SUCCESS + FAILED + 1))/$TOTAL] Indexando: $repo_name"
  echo "  📂 Path: $REPO_PATH"

  export REPO_ROOT="$REPO_PATH"

  if (cd "$INDEXER_DIR" && PYTHONPATH=. python -m indexer index --repo-root "$REPO_PATH"); then
    SUCCESS=$((SUCCESS + 1))
    echo "  ✅ $repo_name indexado com sucesso"
  else
    FAILED=$((FAILED + 1))
    FAILED_REPOS+=("$repo_name")
    echo "  ❌ $repo_name falhou na indexação"
  fi

  echo ""
done

# ── Resumo ──────────────────────────────────────────────────
echo "════════════════════════════════════════════"
echo "📊 Resumo da indexação"
echo "────────────────────────────────────────────"
echo "  Total:     $TOTAL"
echo "  Sucesso:   $SUCCESS"
echo "  Falhas:    $FAILED"

if [[ ${#FAILED_REPOS[@]} -gt 0 ]]; then
  echo "  Com erro:  ${FAILED_REPOS[*]}"
fi

echo "════════════════════════════════════════════"

# Exit code reflete se houve falhas
[[ $FAILED -eq 0 ]]
