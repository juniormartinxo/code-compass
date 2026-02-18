import { Injectable, Logger } from '@nestjs/common';
import axios, { AxiosError, AxiosInstance } from 'axios';

import { resolveQdrantConfig } from './config';
import { ToolExecutionError } from './errors';
import {
  CollectionContentType,
  CollectionMeta,
  ContentType,
  QdrantSearchHit,
  QdrantSearchOutput,
  QdrantSearchResponse,
} from './types';

interface SearchPointsArgs {
  vector: number[];
  topK: number;
  pathPrefix?: string;
  repos?: string[];
  contentType: ContentType;
  strict: boolean;
}

type CollectionTarget = {
  name: string;
  contentType: CollectionContentType;
};

type SearchCollectionResult = {
  hits: QdrantSearchHit[];
  meta: CollectionMeta;
};

class QdrantCollectionQueryError extends Error {
  constructor(
    message: string,
    public readonly meta: CollectionMeta,
  ) {
    super(message);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function inferContentType(path: unknown): CollectionContentType {
  if (typeof path !== 'string') {
    return 'code';
  }
  const normalized = path.toLowerCase();
  if (
    normalized.includes('/docs/')
    || normalized.includes('/adr')
    || normalized.endsWith('/readme.md')
    || normalized.endsWith('.md')
    || normalized.endsWith('.mdx')
    || normalized.endsWith('.rst')
    || normalized.endsWith('.adoc')
    || normalized.endsWith('.txt')
  ) {
    return 'docs';
  }
  return 'code';
}

@Injectable()
export class QdrantService {
  private readonly logger = new Logger(QdrantService.name);
  private readonly config = resolveQdrantConfig(process.env);
  private readonly httpClient: AxiosInstance;

  constructor() {
    this.httpClient = axios.create({
      baseURL: this.config.url,
      timeout: this.config.timeoutMs,
      headers: this.config.apiKey
        ? {
            'api-key': this.config.apiKey,
          }
        : undefined,
    });
  }

  getCollectionName(): string {
    // Compatibilidade legada: manter string singular.
    return this.config.codeCollection;
  }

  async searchPoints(args: SearchPointsArgs): Promise<QdrantSearchOutput> {
    const mocked = this.searchPointsFromMock(args);
    if (mocked) {
      return mocked;
    }

    const targets = this.resolveTargets(args.contentType);
    if (targets.length === 1) {
      const single = await this.searchCollection(targets[0], args);
      return {
        hits: single.hits.slice(0, args.topK),
        collection: targets[0].name,
        collections: [single.meta],
      };
    }

    const settled = await Promise.allSettled(
      targets.map((target) => this.searchCollection(target, args)),
    );

    const collections: CollectionMeta[] = [];
    const successful: SearchCollectionResult[] = [];
    const failures: QdrantCollectionQueryError[] = [];

    for (const result of settled) {
      if (result.status === 'fulfilled') {
        successful.push(result.value);
        collections.push(result.value.meta);
        continue;
      }

      const reason = result.reason;
      if (reason instanceof QdrantCollectionQueryError) {
        failures.push(reason);
        collections.push(reason.meta);
      } else {
        this.logger.error('Erro inesperado ao consultar coleção do Qdrant');
      }
    }

    if (args.strict && failures.length > 0) {
      throw new ToolExecutionError(
        'QDRANT_UNAVAILABLE',
        'Falha ao consultar Qdrant em modo strict',
      );
    }

    if (failures.length > 0) {
      for (const meta of collections) {
        if (meta.status === 'ok') {
          meta.status = 'partial';
        }
      }
    }

    // Caso explícito: se ambas as coleções falharem (mesmo com strict=false), não há retorno parcial possível.
    if (successful.length === 0) {
      throw new ToolExecutionError(
        'QDRANT_UNAVAILABLE',
        'Falha ao consultar Qdrant: coleções code/docs indisponíveis',
      );
    }

    const codeHits = successful.find((item) => item.meta.contentType === 'code')?.hits ?? [];
    const docsHits = successful.find((item) => item.meta.contentType === 'docs')?.hits ?? [];
    const merged = this.mergeByRrf(codeHits, docsHits, args.topK);

    return {
      hits: merged,
      collection: this.config.codeCollection,
      collections,
    };
  }

  private resolveTargets(contentType: ContentType): CollectionTarget[] {
    if (contentType === 'code') {
      return [{ name: this.config.codeCollection, contentType: 'code' }];
    }
    if (contentType === 'docs') {
      return [{ name: this.config.docsCollection, contentType: 'docs' }];
    }
    return [
      { name: this.config.codeCollection, contentType: 'code' },
      { name: this.config.docsCollection, contentType: 'docs' },
    ];
  }

  private async searchCollection(
    target: CollectionTarget,
    args: SearchPointsArgs,
  ): Promise<SearchCollectionResult> {
    const body: Record<string, unknown> = {
      vector: args.vector,
      limit: args.topK,
      with_payload: true,
      with_vector: false,
    };

    const must: unknown[] = [];
    if (args.pathPrefix) {
      must.push({
        key: 'path',
        match: {
          text: args.pathPrefix,
        },
      });
    }

    if (Array.isArray(args.repos) && args.repos.length > 0) {
      if (args.repos.length === 1) {
        must.push({
          key: 'repo',
          match: {
            value: args.repos[0],
          },
        });
      } else {
        must.push({
          should: args.repos.map((repo) => ({
            key: 'repo',
            match: {
              value: repo,
            },
          })),
        });
      }
    }

    must.push({
      key: 'content_type',
      match: {
        value: target.contentType,
      },
    });

    body.filter = { must };

    const started = Date.now();
    try {
      const response = await this.httpClient.post<QdrantSearchResponse>(
        `/collections/${encodeURIComponent(target.name)}/points/search`,
        body,
      );
      const results = response.data?.result;
      const hits = Array.isArray(results) ? results.slice(0, args.topK) : [];

      return {
        hits,
        meta: {
          name: target.name,
          contentType: target.contentType,
          hits: hits.length,
          latencyMs: Date.now() - started,
          status: 'ok',
        },
      };
    } catch (error) {
      const latencyMs = Date.now() - started;
      let message = `Falha ao consultar Qdrant collection=${target.name}`;

      if (axios.isAxiosError(error)) {
        const status = (error as AxiosError).response?.status;
        message = `${message} status=${status ?? 'unknown'}`;
        this.logger.error(message);
      } else {
        this.logger.error(message);
      }

      throw new QdrantCollectionQueryError(message, {
        name: target.name,
        contentType: target.contentType,
        hits: 0,
        latencyMs,
        status: 'unavailable',
      });
    }
  }

  private mergeByRrf(
    codeResults: QdrantSearchHit[],
    docsResults: QdrantSearchHit[],
    topK: number,
  ): QdrantSearchHit[] {
    const ranked = [
      ...codeResults.map((hit, i) => ({
        hit,
        type: 'code' as const,
        rrf: this.rrfScore(i + 1),
      })),
      ...docsResults.map((hit, i) => ({
        hit,
        type: 'docs' as const,
        rrf: this.rrfScore(i + 1),
      })),
    ].sort((a, b) => b.rrf - a.rrf);

    const accepted: QdrantSearchHit[] = [];
    const deferred: Array<{ hit: QdrantSearchHit; type: CollectionContentType; rrf: number }> = [];
    const perType = { code: 0, docs: 0 };
    const effectiveFloor = Math.min(this.config.diversityFloor, Math.floor(topK / 2));

    for (const item of ranked) {
      if (effectiveFloor > 0 && perType[item.type] < effectiveFloor) {
        accepted.push(item.hit);
        perType[item.type] += 1;
        continue;
      }
      deferred.push(item);
    }

    for (const item of deferred) {
      if (accepted.length >= topK) {
        break;
      }
      accepted.push(item.hit);
    }

    return accepted.slice(0, topK);
  }

  private rrfScore(rank: number): number {
    return 1 / (this.config.rrfK + rank);
  }

  private searchPointsFromMock(args: SearchPointsArgs): QdrantSearchOutput | null {
    const raw = process.env.MCP_QDRANT_MOCK_RESPONSE;
    if (!raw) {
      return null;
    }

    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return {
          hits: [],
          collection: this.config.codeCollection,
          collections: [],
        };
      }

      const hits = parsed.filter(isRecord) as QdrantSearchHit[];
      const byPath = args.pathPrefix
        ? hits.filter((hit) => {
            if (!isRecord(hit.payload)) {
              return false;
            }
            const path = hit.payload.path;
            return typeof path === 'string' && path.startsWith(args.pathPrefix ?? '');
          })
        : hits;

      const byRepo = Array.isArray(args.repos) && args.repos.length > 0
        ? byPath.filter((hit) => {
            if (!isRecord(hit.payload)) {
              return false;
            }
            const repo = hit.payload.repo;
            return typeof repo === 'string' && args.repos?.includes(repo);
          })
        : byPath;

      const normalized = byRepo.map((hit) => {
        const payload = isRecord(hit.payload) ? hit.payload : {};
        const existing = payload.content_type;
        const contentType = existing === 'docs' || existing === 'code'
          ? existing
          : inferContentType(payload.path);

        return {
          ...hit,
          payload: {
            ...payload,
            content_type: contentType,
          },
        };
      });

      const codeHits = normalized.filter(
        (hit) => isRecord(hit.payload) && hit.payload.content_type === 'code',
      );
      const docsHits = normalized.filter(
        (hit) => isRecord(hit.payload) && hit.payload.content_type === 'docs',
      );

      if (args.contentType === 'code') {
        return {
          hits: codeHits.slice(0, args.topK),
          collection: this.config.codeCollection,
          collections: [
            {
              name: this.config.codeCollection,
              contentType: 'code',
              hits: codeHits.length,
              latencyMs: 0,
              status: 'ok',
            },
          ],
        };
      }

      if (args.contentType === 'docs') {
        return {
          hits: docsHits.slice(0, args.topK),
          collection: this.config.docsCollection,
          collections: [
            {
              name: this.config.docsCollection,
              contentType: 'docs',
              hits: docsHits.length,
              latencyMs: 0,
              status: 'ok',
            },
          ],
        };
      }

      return {
        hits: this.mergeByRrf(codeHits, docsHits, args.topK),
        collection: this.config.codeCollection,
        collections: [
          {
            name: this.config.codeCollection,
            contentType: 'code',
            hits: codeHits.length,
            latencyMs: 0,
            status: 'ok',
          },
          {
            name: this.config.docsCollection,
            contentType: 'docs',
            hits: docsHits.length,
            latencyMs: 0,
            status: 'ok',
          },
        ],
      };
    } catch {
      this.logger.warn('MCP_QDRANT_MOCK_RESPONSE inválido; ignorando mock');
      return {
        hits: [],
        collection: this.config.codeCollection,
        collections: [],
      };
    }
  }
}
