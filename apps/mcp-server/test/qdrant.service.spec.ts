import nock from 'nock';
import { afterEach, describe, expect, it } from 'vitest';

import { QdrantService } from '../src/qdrant.service';

describe('QdrantService', () => {
  afterEach(() => {
    nock.cleanAll();
    delete process.env.QDRANT_URL;
    delete process.env.QDRANT_COLLECTION;
    delete process.env.QDRANT_API_KEY;
  });

  it('deve mapear resposta /points/search respeitando topK', async () => {
    process.env.QDRANT_URL = 'http://localhost:6333';
    process.env.QDRANT_COLLECTION = 'compass__3584__manutic_nomic_embed_code';

    nock('http://localhost:6333')
      .post('/collections/compass__3584__manutic_nomic_embed_code/points/search')
      .reply(200, {
        result: [
          {
            score: 0.8,
            payload: { path: 'src/a.ts' },
          },
          {
            score: 0.7,
            payload: { path: 'src/b.ts' },
          },
        ],
      });

    const service = new QdrantService();
    const hits = await service.searchPoints({
      vector: [0.1, 0.2],
      topK: 1,
      pathPrefix: 'src/',
    });

    expect(hits).toHaveLength(1);
    expect(hits[0].score).toBe(0.8);
  });

  it('deve enviar filtro de repo quando repos for informado', async () => {
    process.env.QDRANT_URL = 'http://localhost:6333';
    process.env.QDRANT_COLLECTION = 'compass__3584__manutic_nomic_embed_code';

    nock('http://localhost:6333')
      .post('/collections/compass__3584__manutic_nomic_embed_code/points/search', (body: Record<string, unknown>) => {
        const filter = body.filter as { must?: Array<Record<string, unknown>> } | undefined;
        const must = filter?.must ?? [];
        return must.some((item) => {
          const match = item.match as { value?: string } | undefined;
          return item.key === 'repo' && match?.value === 'acme-repo';
        });
      })
      .reply(200, {
        result: [],
      });

    const service = new QdrantService();
    const hits = await service.searchPoints({
      vector: [0.1, 0.2],
      topK: 1,
      repos: ['acme-repo'],
    });

    expect(hits).toHaveLength(0);
  });
});
