code-compass/
  README.md
  AGENTS.md
  .env.example
  .gitignore
  Makefile
  package.json
  pnpm-workspace.yaml

  apps/
    mcp-server/                 # Node/NestJS - expõe tools MCP
      src/
        main.ts                 # entrypoint
        app.module.ts           # módulo NestJS
        ask-code.tool.ts        # tool RAG (embedding + busca + LLM)
        search-code.tool.ts     # tool de busca semântica
        open-file.tool.ts       # tool de leitura de arquivos
        qdrant.service.ts       # cliente Qdrant
        file.service.ts         # serviço de filesystem
        mcp-stdio.server.ts     # transporte STDIO/NDJSON
        mcp-http.controller.ts  # transporte HTTP/JSON-RPC
        mcp-protocol.handler.ts # handler do protocolo MCP
        config.ts               # configurações
        scope.ts                # resolução de escopo
        types.ts                # tipos TypeScript
        errors.ts               # classes de erro
        repo-root.ts            # resolução de repo root
        env-loader.ts           # carregador de .env
        transport.ts            # utilitários de transporte
      test/                     # testes unitários e integração
      scripts/                  # scripts de teste STDIO
      package.json
      tsconfig.json
      nest-cli.json
      vitest.config.ts

    indexer/                     # Python - ingest/chunk/embed/upsert
      indexer/
        __init__.py
        __main__.py              # CLI principal (init, index, search, ask, etc.)
        chunk.py                 # chunking de arquivos
        config.py                # configurações e env vars
        embedder.py              # cliente Ollama para embeddings
        env.py                   # carregador de .env
        qdrant_store.py          # cliente Qdrant
        scan.py                  # scanner de repositório
      scripts/
        search.py                # script de busca standalone
      tests/                     # testes pytest
      requirements.txt
      README.md

    docs/                        # Portal de documentação (Nextra/Next.js)
      pages/
        ARCHITECTURE.md          # arquitetura do sistema
        STRUCTURE.md             # estrutura de diretórios
        ADRs/                    # Architecture Decision Records
        indexer/                 # docs do indexer
          commands/              # docs de comandos
        mcp-server/              # docs do MCP server
        cli/                     # docs da CLI
        tutoriais/               # tutoriais
      public/
      styles/
      theme.config.jsx
      next.config.mjs
      package.json

    cli/                         # CLI Python (Typer + Rich)
      src/code_compass_cli/
        app.py                   # CLI principal
        config.py                # configurações
        toad_acp.py              # integração Toad/ACP
      pyproject.toml
      README.md
      TROUBLESHOOTING.md

    acp/                         # Agente ACP (Agent Client Protocol)
      src/code_compass_acp/
        __init__.py
        __main__.py              # entrypoint
        agent.py                 # agente ACP
        bridge.py                # bridge MCP/ACP
        chunker.py               # chunking
      scripts/
        e2e_smoke.py             # teste E2E
      tests/
      pyproject.toml
      README.md

  bin/
    dev-chat                     # launcher TUI chat
    dev-mcp                      # launcher MCP server

  code-base/                     # repositórios a indexar (gitignored)
    .gitkeep

  infra/
    docker-compose.yml           # Qdrant local

  scripts/
    index-all.sh                 # indexa todos os repos de code-base/

  .agents/                       # skills para agentes de IA
    skills/
      developer-*/               # skills por domínio
