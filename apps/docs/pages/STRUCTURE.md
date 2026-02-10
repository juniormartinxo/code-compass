code-compass/
  README.md
  LICENSE

  .env.example
  .gitignore
  Makefile

  apps/
    mcp-server/                 # Node/NestJS - expõe tools MCP
      src/
        main.ts
        mcp/                     # handlers MCP / transport (stdio/http)
        modules/
        services/
        adapters/                # qdrant/fs/git adapters
        config/
      test/
      package.json
      tsconfig.json
      Dockerfile

    indexer/                     # Python - ingest/chunk/embed/upsert
      code_compass/
        __init__.py
        cli.py                   # entrypoint `python -m code_compass ...`
        index/
          full.py
          incremental.py
        chunking/
          ast/
          heuristics/
        embeddings/
          providers/             # openai/local/etc
        storage/
          qdrant.py
        utils/
      tests/
      requirements.txt
      pyproject.toml             # (recomendado) ou mantenha só requirements
      Dockerfile

  packages/
    shared/                      # contratos compartilhados (schemas, tipos)
      mcp/
        tools.schema.json        # definição dos tools (entrada/saída)
      search/
        query.schema.json
      README.md

  infra/
    docker-compose.yml           # Qdrant local
    qdrant/
      collections/               # bootstrap (opcional)
      snapshots/                 # (opcional) dumps dev
    observability/               # (opcional) prom/grafana/loki

  scripts/
    dev/
      bootstrap.sh               # setup local (deps, env, hooks)
    ci/
      lint.sh
      test.sh
      build.sh
      index-smoke.sh             # sanity: indexa repo pequeno
    ops/
      backup-qdrant.sh
      restore-qdrant.sh

  docs/
    architecture/
      overview.md
      decisions/
        ADR-0001-stack.md
    operations/
      runbook.md
      troubleshooting.md
    security/
      threat-model.md
      allowlist-blocklist.md
      secrets-redaction.md
    api/
      mcp-tools.md               # doc das tools (search_code/open_file/list_tree)

  .github/
    workflows/
      ci.yml
      release.yml

  .agents/                       # se você for usar no repo (opcional)
    skills/
      developer/
        SKILL.md
        agents/
        references/

  .vscode/
    settings.json
