# Tutorial: Indexar um repositório específico

Este tutorial mostra como indexar **um repositório específico** com o comando `index`, apontando explicitamente o `repo-root`. Se você usa múltiplos repos dentro de `code-base/`, repita o processo para cada repo.

## Pré-requisitos
- Provider de embeddings em execução (`EMBEDDING_PROVIDER_CODE_API_URL` e `EMBEDDING_PROVIDER_DOCS_API_URL`) e modelos configurados (`EMBEDDING_MODEL_CODE` e `EMBEDDING_MODEL_DOCS`).
- Qdrant acessível (`QDRANT_URL`).
- Repositório disponível em disco (pasta local).

Observações importantes:
- O scanner ignora arquivos binários.
- O scanner **não** segue symlinks.
- O `index` filtra por extensão e diretórios, então ajuste `--allow-exts` e `--ignore-dirs` se necessário.

## Passo a passo

1. Valide com `scan` se o repositório alvo está sendo lido corretamente.

```bash
python -m indexer scan --repo-root /caminho/do/repositorio
```

2. Execute a indexação do repositório.

```bash
python -m indexer index --repo-root /caminho/do/repositorio
```

### Multi-repo (code-base)

Se o host mantém vários repos em `code-base/`, rode a indexação por repo:

```bash
for repo in code-base/*; do
  [ -d "$repo" ] || continue
  python -m indexer index --repo-root "$repo"
done
```

3. Confira se a indexação está acessível via busca.

```bash
python -m indexer search "palavra-chave" --path_prefix caminho/relativo
```

4. (Opcional) Valide pergunta RAG no repo indexado.

```bash
python -m indexer ask "qual a arquitetura principal deste repo?" --scope-repo $(basename /caminho/do/repositorio)
```

## Variações úteis

### Limitar extensões

```bash
python -m indexer index --repo-root /caminho/do/repositorio --allow-exts .ts,.tsx,.py
```

### Ignorar diretórios adicionais

```bash
python -m indexer index --repo-root /caminho/do/repositorio --ignore-dirs .git,node_modules,dist,build
```

### Indexação rápida para teste

```bash
python -m indexer index --repo-root /caminho/do/repositorio --max-files 20
```

## Problemas comuns

- O repositório não aparece no `scan`.
Verifique se o `repo-root` aponta para a pasta correta e se as extensões permitidas incluem os arquivos desejados.
- O `search` não retorna resultados.
Confirme que a indexação concluiu com `status: success` e que a query existe nos arquivos indexados.

## Ver também

- [index](./commands/index.md) - Indexação completa
- [scan](./commands/scan.md) - Listagem de arquivos elegíveis
- [search](./commands/search.md) - Busca semântica na collection
