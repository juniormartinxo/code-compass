import { afterEach, describe, expect, it } from 'vitest';

import { ToolInputError } from '../src/errors';
import { CollectionMeta, QdrantSearchHit } from '../src/types';
import { QdrantService } from '../src/qdrant.service';
import { SearchCodeTool } from '../src/search-code.tool';

class QdrantServiceMock {
  constructor(private readonly hits: QdrantSearchHit[]) {}

  getCollectionName(): string {
    return 'compass_manutic_nomic_embed__code';
  }

  async searchPoints(args: { repos?: string[]; contentType?: 'code' | 'docs' | 'all'; topK?: number }): Promise<{
    hits: QdrantSearchHit[];
    collection: string;
    collections: CollectionMeta[];
  }> {
    if (!Array.isArray(args.repos) || args.repos.length === 0) {
      return {
        hits: this.filterByContentType(this.hits, args.contentType).slice(0, args.topK ?? this.hits.length),
        collection: 'compass_manutic_nomic_embed__code',
        collections: this.defaultCollections(),
      };
    }

    const filtered = this.filterByContentType(this.hits, args.contentType).filter((hit) => {
      const payload = hit.payload as Record<string, unknown> | undefined;
      const repo = payload?.repo;
      return typeof repo === 'string' && args.repos.includes(repo);
    });
    return {
      hits: filtered,
      collection: 'compass_manutic_nomic_embed__code',
      collections: this.defaultCollections(),
    };
  }

  private defaultCollections(): CollectionMeta[] {
    return [
      {
        name: 'compass_manutic_nomic_embed__code',
        contentType: 'code',
        hits: this.hits.length,
        latencyMs: 1,
        status: 'ok',
      },
      {
        name: 'compass_manutic_nomic_embed__docs',
        contentType: 'docs',
        hits: this.hits.length,
        latencyMs: 1,
        status: 'ok',
      },
    ];
  }

  private filterByContentType(
    hits: QdrantSearchHit[],
    contentType: 'code' | 'docs' | 'all' | undefined,
  ): QdrantSearchHit[] {
    if (!contentType || contentType === 'all') {
      return hits;
    }
    return hits.filter((hit) => {
      const payload = hit.payload as Record<string, unknown> | undefined;
      return payload?.content_type === contentType;
    });
  }
}

function createHits(): QdrantSearchHit[] {
  return [
    {
      score: 0.9123,
      payload: {
        repo: 'acme-repo',
        path: 'src/foo.ts',
        start_line: 10,
        end_line: 42,
        text: 'const  a = 1;\n\nconst b=2;',
        content_type: 'code',
      },
    },
    {
      score: 0.8,
      payload: {
        repo: 'shared-lib',
        path: 'src/shared.ts',
        startLine: 3,
        endLine: 9,
        text: 'export const shared = true;',
        content_type: 'code',
      },
    },
  ];
}

describe('SearchCodeTool', () => {
  afterEach(() => {
    delete process.env.ALLOW_GLOBAL_SCOPE;
  });

  it('deve aplicar clamp de topK e mapear payload snake_case (scope repo)', async () => {
    const mock = new QdrantServiceMock(createHits());
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      scope: { type: 'repo', repo: 'acme-repo' },
      query: '  find foo  ',
      topK: 200,
      vector: [0.1, 0.2],
    });

    expect(output.meta.repo).toBe('acme-repo');
    expect(output.meta.scope).toEqual({ type: 'repo', repos: ['acme-repo'] });
    expect(output.meta.topK).toBe(20);
    expect(output.meta.contentType).toBe('all');
    expect(output.meta.strict).toBe(false);
    expect(output.results).toHaveLength(1);
    expect(output.results[0]).toEqual({
      repo: 'acme-repo',
      score: 0.9123,
      path: 'src/foo.ts',
      startLine: 10,
      endLine: 42,
      snippet: 'const a = 1; const b=2;',
      contentType: 'code',
    });
  });

  it('deve truncar snippet longo para 300 chars', async () => {
    const longText = ` ${'abc '.repeat(120)} `;
    const mock = new QdrantServiceMock([
      {
        score: 0.3,
        payload: {
          repo: 'acme-repo',
          path: 'src/long.ts',
          startLine: 1,
          endLine: 2,
          text: longText,
          content_type: 'code',
        },
      },
    ]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      scope: { type: 'repo', repo: 'acme-repo' },
      query: 'snippet',
      topK: 1,
      vector: [0.2, 0.4],
    });

    expect(output.results[0].repo).toBe('acme-repo');
    expect(output.results[0].snippet.length).toBeLessThanOrEqual(300);
    expect(output.results[0].snippet.endsWith('...')).toBe(true);
  });

  it('deve retornar (no snippet) quando payload.text não existe', async () => {
    const mock = new QdrantServiceMock([
      {
        score: 0.8,
        payload: {
          repo: 'acme-repo',
          path: 'src/no-text.ts',
          startLine: 3,
          endLine: 9,
          content_type: 'code',
        },
      },
    ]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      scope: { type: 'repo', repo: 'acme-repo' },
      query: 'without text',
      topK: 1,
      vector: [1],
    });

    expect(output.results[0].repo).toBe('acme-repo');
    expect(output.results[0].snippet).toBe('(no snippet)');
  });

  it('deve rejeitar pathPrefix inválido', async () => {
    const mock = new QdrantServiceMock([]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    await expect(
      tool.execute({
        scope: { type: 'repo', repo: 'acme-repo' },
        query: 'test',
        topK: 1,
        pathPrefix: '../src',
        vector: [0.1],
      }),
    ).rejects.toBeInstanceOf(ToolInputError);
  });

  it('deve falhar sem vetor quando não há embeddings no Node', async () => {
    const mock = new QdrantServiceMock([]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    await expect(
      tool.execute({
        scope: { type: 'repo', repo: 'acme-repo' },
        query: 'abc',
      }),
    ).rejects.toBeInstanceOf(ToolInputError);
  });

  it('deve falhar sem scope', async () => {
    const mock = new QdrantServiceMock([]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    await expect(
      tool.execute({
        query: 'abc',
        vector: [0.1],
      }),
    ).rejects.toBeInstanceOf(ToolInputError);
  });

  it('deve aceitar scope repo sem repo no root do input', async () => {
    const mock = new QdrantServiceMock(createHits());
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      scope: { type: 'repo', repo: 'acme-repo' },
      query: 'find foo',
      topK: 10,
      vector: [0.1, 0.2],
    });

    expect(output.meta.scope).toEqual({ type: 'repo', repos: ['acme-repo'] });
    expect(output.meta.repo).toBe('acme-repo');
    expect(output.results).toHaveLength(1);
    expect(output.results[0].repo).toBe('acme-repo');
  });

  it('deve aceitar scope repos', async () => {
    const mock = new QdrantServiceMock(createHits());
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      scope: { type: 'repos', repos: ['acme-repo', 'shared-lib'] },
      query: 'find shared',
      topK: 10,
      vector: [0.1, 0.2],
    });

    expect(output.meta.scope).toEqual({ type: 'repos', repos: ['acme-repo', 'shared-lib'] });
    expect(output.results).toHaveLength(2);
  });

  it('deve bloquear scope all sem flag', async () => {
    const mock = new QdrantServiceMock(createHits());
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    await expect(
      tool.execute({
        scope: { type: 'all' },
        query: 'find shared',
        topK: 10,
        vector: [0.1, 0.2],
      }),
    ).rejects.toMatchObject({
      code: 'FORBIDDEN',
    });
  });

  it('deve aceitar scope all com flag habilitada', async () => {
    process.env.ALLOW_GLOBAL_SCOPE = 'true';
    const mock = new QdrantServiceMock(createHits());
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      scope: { type: 'all' },
      query: 'find shared',
      topK: 10,
      vector: [0.1, 0.2],
    });

    expect(output.meta.scope).toEqual({ type: 'all' });
    expect(output.results).toHaveLength(2);
    expect(output.results.map((item) => item.repo)).toEqual(expect.arrayContaining(['acme-repo', 'shared-lib']));
  });

  it('deve aceitar filtro contentType e strict', async () => {
    process.env.ALLOW_GLOBAL_SCOPE = 'true';
    const mock = new QdrantServiceMock([
      {
        score: 0.9,
        payload: {
          repo: 'acme-repo',
          path: 'docs/guide.md',
          startLine: 1,
          endLine: 5,
          text: 'Guia',
          content_type: 'docs',
        },
      },
      {
        score: 0.7,
        payload: {
          repo: 'acme-repo',
          path: 'src/main.ts',
          startLine: 1,
          endLine: 5,
          text: 'Code',
          content_type: 'code',
        },
      },
    ]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      scope: { type: 'all' },
      query: 'find docs',
      topK: 10,
      vector: [0.1, 0.2],
      contentType: 'docs',
      strict: true,
    });

    expect(output.meta.contentType).toBe('docs');
    expect(output.meta.strict).toBe(true);
    expect(output.results).toHaveLength(1);
    expect(output.results[0].contentType).toBe('docs');
  });
});
