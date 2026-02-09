import { Injectable, Logger } from '@nestjs/common';
import axios, { AxiosError, AxiosInstance } from 'axios';

import { resolveQdrantConfig } from './config';
import { ToolInputError } from './errors';
import { QdrantSearchHit, QdrantSearchResponse } from './types';

interface SearchPointsArgs {
  vector: number[];
  topK: number;
  pathPrefix?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
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
    return this.config.collection;
  }

  async searchPoints(args: SearchPointsArgs): Promise<QdrantSearchHit[]> {
    const mocked = this.searchPointsFromMock(args);
    if (mocked) {
      return mocked;
    }

    const body: Record<string, unknown> = {
      vector: args.vector,
      limit: args.topK,
      with_payload: true,
      with_vector: false,
    };

    if (args.pathPrefix) {
      body.filter = {
        must: [
          {
            key: 'path',
            match: {
              text: args.pathPrefix,
            },
          },
        ],
      };
    }

    try {
      const response = await this.httpClient.post<QdrantSearchResponse>(
        `/collections/${encodeURIComponent(this.config.collection)}/points/search`,
        body,
      );
      const results = response.data?.result;
      if (!Array.isArray(results)) {
        return [];
      }
      return results.slice(0, args.topK);
    } catch (error) {
      if (error instanceof ToolInputError) {
        throw error;
      }

      if (axios.isAxiosError(error)) {
        const status = (error as AxiosError).response?.status;
        this.logger.error(
          `Erro ao consultar Qdrant collection=${this.config.collection} status=${status ?? 'unknown'}`,
        );
      } else {
        this.logger.error('Erro inesperado ao consultar Qdrant');
      }
      throw new Error('Falha ao consultar Qdrant');
    }
  }

  private searchPointsFromMock(args: SearchPointsArgs): QdrantSearchHit[] | null {
    const raw = process.env.MCP_QDRANT_MOCK_RESPONSE;
    if (!raw) {
      return null;
    }

    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return [];
      }

      const hits = parsed.filter(isRecord) as QdrantSearchHit[];
      const filtered = args.pathPrefix
        ? hits.filter((hit) => {
            if (!isRecord(hit.payload)) {
              return false;
            }
            const path = hit.payload.path;
            return typeof path === 'string' && path.startsWith(args.pathPrefix ?? '');
          })
        : hits;

      return filtered.slice(0, args.topK);
    } catch {
      this.logger.warn('MCP_QDRANT_MOCK_RESPONSE inválido; ignorando mock');
      return [];
    }
  }
}
