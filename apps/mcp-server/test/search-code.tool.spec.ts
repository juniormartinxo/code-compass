import { describe, expect, it } from 'vitest';

import { ToolInputError } from '../src/errors';
import { QdrantSearchHit } from '../src/types';
import { QdrantService } from '../src/qdrant.service';
import { SearchCodeTool } from '../src/search-code.tool';

class QdrantServiceMock {
  constructor(private readonly hits: QdrantSearchHit[]) {}

  getCollectionName(): string {
    return 'code_chunks';
  }

  async searchPoints(): Promise<QdrantSearchHit[]> {
    return this.hits;
  }
}

describe('SearchCodeTool', () => {
  it('deve aplicar clamp de topK e mapear payload snake_case', async () => {
    const mock = new QdrantServiceMock([
      {
        score: 0.9123,
        payload: {
          path: 'src/foo.ts',
          start_line: 10,
          end_line: 42,
          text: 'const  a = 1;\n\nconst b=2;',
        },
      },
    ]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      repo: 'acme-repo',
      query: '  find foo  ',
      topK: 200,
      vector: [0.1, 0.2],
    });

    expect(output.meta.repo).toBe('acme-repo');
    expect(output.meta.topK).toBe(20);
    expect(output.results).toHaveLength(1);
    expect(output.results[0]).toEqual({
      score: 0.9123,
      path: 'src/foo.ts',
      startLine: 10,
      endLine: 42,
      snippet: 'const a = 1; const b=2;',
    });
  });

  it('deve truncar snippet longo para 300 chars', async () => {
    const longText = ` ${'abc '.repeat(120)} `;
    const mock = new QdrantServiceMock([
      {
        score: 0.3,
        payload: {
          path: 'src/long.ts',
          startLine: 1,
          endLine: 2,
          text: longText,
        },
      },
    ]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      repo: 'acme-repo',
      query: 'snippet',
      topK: 1,
      vector: [0.2, 0.4],
    });

    expect(output.results[0].snippet.length).toBeLessThanOrEqual(300);
    expect(output.results[0].snippet.endsWith('...')).toBe(true);
  });

  it('deve retornar (no snippet) quando payload.text não existe', async () => {
    const mock = new QdrantServiceMock([
      {
        score: 0.8,
        payload: {
          path: 'src/no-text.ts',
          startLine: 3,
          endLine: 9,
        },
      },
    ]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    const output = await tool.execute({
      repo: 'acme-repo',
      query: 'without text',
      topK: 1,
      vector: [1],
    });

    expect(output.results[0].snippet).toBe('(no snippet)');
  });

  it('deve rejeitar pathPrefix inválido', async () => {
    const mock = new QdrantServiceMock([]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    await expect(
      tool.execute({
        repo: 'acme-repo',
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
        repo: 'acme-repo',
        query: 'abc',
      }),
    ).rejects.toBeInstanceOf(ToolInputError);
  });

  it('deve falhar sem repo', async () => {
    const mock = new QdrantServiceMock([]);
    const tool = new SearchCodeTool(mock as unknown as QdrantService);

    await expect(
      tool.execute({
        query: 'abc',
        vector: [0.1],
      }),
    ).rejects.toBeInstanceOf(ToolInputError);
  });
});
