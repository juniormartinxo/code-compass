import nock from 'nock';
import { afterEach, describe, expect, it } from 'vitest';

import { QdrantService } from '../src/qdrant.service';

const STEM = 'compass__3584__manutic_nomic_embed_code';
const CODE_COLLECTION = `${STEM}__code`;
const DOCS_COLLECTION = `${STEM}__docs`;

describe('QdrantService', () => {
  afterEach(() => {
    nock.cleanAll();
    delete process.env.QDRANT_URL;
    delete process.env.QDRANT_COLLECTION;
    delete process.env.QDRANT_COLLECTION_BASE;
    delete process.env.QDRANT_COLLECTION_CODE;
    delete process.env.QDRANT_COLLECTION_DOCS;
    delete process.env.QDRANT_API_KEY;
    delete process.env.RRF_K;
    delete process.env.RRF_DIVERSITY_FLOOR;
  });

  it('deve buscar em coleção code respeitando topK', async () => {
    process.env.QDRANT_URL = 'http://localhost:6333';
    process.env.QDRANT_COLLECTION_BASE = STEM;

    nock('http://localhost:6333')
      .post(`/collections/${CODE_COLLECTION}/points/search`)
      .reply(200, {
        result: [
          { score: 0.8, payload: { path: 'src/a.ts', content_type: 'code' } },
          { score: 0.7, payload: { path: 'src/b.ts', content_type: 'code' } },
        ],
      });

    const service = new QdrantService();
    const result = await service.searchPoints({
      vector: [0.1, 0.2],
      topK: 1,
      pathPrefix: 'src/',
      contentType: 'code',
      strict: false,
    });

    expect(result.hits).toHaveLength(1);
    expect(result.hits[0].score).toBe(0.8);
    expect(result.collection).toBe(CODE_COLLECTION);
    expect(result.collections[0].status).toBe('ok');
  });

  it('deve usar merge por RRF quando contentType=all', async () => {
    process.env.QDRANT_URL = 'http://localhost:6333';
    process.env.QDRANT_COLLECTION_BASE = STEM;

    nock('http://localhost:6333')
      .post(`/collections/${CODE_COLLECTION}/points/search`)
      .reply(200, {
        result: [
          { score: 0.91, payload: { path: 'src/code.ts', content_type: 'code' } },
        ],
      });

    nock('http://localhost:6333')
      .post(`/collections/${DOCS_COLLECTION}/points/search`)
      .reply(200, {
        result: [
          { score: 0.62, payload: { path: 'docs/guide.md', content_type: 'docs' } },
        ],
      });

    const service = new QdrantService();
    const result = await service.searchPoints({
      vector: [0.1, 0.2],
      topK: 2,
      contentType: 'all',
      strict: false,
    });

    expect(result.hits).toHaveLength(2);
    expect(result.collections).toHaveLength(2);
    expect(result.collections.map((item) => item.status)).toEqual(['ok', 'ok']);
  });

  it('deve retornar parcial com strict=false quando uma coleção falha', async () => {
    process.env.QDRANT_URL = 'http://localhost:6333';
    process.env.QDRANT_COLLECTION_BASE = STEM;

    nock('http://localhost:6333')
      .post(`/collections/${CODE_COLLECTION}/points/search`)
      .reply(503, { status: 'unavailable' });

    nock('http://localhost:6333')
      .post(`/collections/${DOCS_COLLECTION}/points/search`)
      .reply(200, {
        result: [
          { score: 0.62, payload: { path: 'docs/guide.md', content_type: 'docs' } },
        ],
      });

    const service = new QdrantService();
    const result = await service.searchPoints({
      vector: [0.1, 0.2],
      topK: 5,
      contentType: 'all',
      strict: false,
    });

    expect(result.hits).toHaveLength(1);
    expect(result.collections.find((item) => item.contentType === 'code')?.status).toBe('unavailable');
    expect(result.collections.find((item) => item.contentType === 'docs')?.status).toBe('partial');
  });

  it('deve falhar com strict=true quando uma coleção falha', async () => {
    process.env.QDRANT_URL = 'http://localhost:6333';
    process.env.QDRANT_COLLECTION_BASE = STEM;

    nock('http://localhost:6333')
      .post(`/collections/${CODE_COLLECTION}/points/search`)
      .reply(503, { status: 'unavailable' });

    nock('http://localhost:6333')
      .post(`/collections/${DOCS_COLLECTION}/points/search`)
      .reply(200, {
        result: [{ score: 0.7, payload: { path: 'docs/x.md', content_type: 'docs' } }],
      });

    const service = new QdrantService();

    await expect(
      service.searchPoints({
        vector: [0.1, 0.2],
        topK: 5,
        contentType: 'all',
        strict: true,
      }),
    ).rejects.toThrowError('Falha ao consultar Qdrant em modo strict');
  });
});
