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
    process.env.QDRANT_COLLECTION = 'code_chunks';

    nock('http://localhost:6333')
      .post('/collections/code_chunks/points/search')
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
});
