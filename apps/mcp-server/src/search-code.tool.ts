import { Injectable } from '@nestjs/common';

import { ToolInputError } from './errors';
import { QdrantService } from './qdrant.service';
import { QdrantSearchHit, SearchCodeInput, SearchCodeOutput } from './types';

const DEFAULT_TOP_K = 10;
const MIN_TOP_K = 1;
const MAX_TOP_K = 20;
const MAX_QUERY_CHARS = 500;
const MAX_PATH_PREFIX_CHARS = 200;
const MAX_SNIPPET_CHARS = 300;
const MIN_SNIPPET_CHARS = 200;

@Injectable()
export class SearchCodeTool {
  constructor(private readonly qdrantService: QdrantService) {}

  async execute(rawInput: unknown): Promise<SearchCodeOutput> {
    const input = this.validateInput(rawInput);
    const hits = await this.qdrantService.searchPoints({
      vector: input.vector,
      topK: input.topK,
      pathPrefix: input.pathPrefix,
    });

    const results = hits.slice(0, input.topK).map((hit) => this.mapHitToResult(hit));

    const meta: SearchCodeOutput['meta'] = {
      topK: input.topK,
      collection: this.qdrantService.getCollectionName(),
    };

    if (input.pathPrefix) {
      meta.pathPrefix = input.pathPrefix;
    }

    return {
      results,
      meta,
    };
  }

  private validateInput(rawInput: unknown): Required<SearchCodeInput> {
    if (!rawInput || typeof rawInput !== 'object') {
      throw new ToolInputError('Input inválido: esperado objeto');
    }

    const input = rawInput as SearchCodeInput;
    const query = this.validateQuery(input.query);
    const topK = this.clampTopK(input.topK);
    const pathPrefix = this.validatePathPrefix(input.pathPrefix);
    const vector = this.validateVector(input.vector);

    return {
      query,
      topK,
      pathPrefix,
      vector,
    };
  }

  private validateQuery(query: unknown): string {
    if (typeof query !== 'string') {
      throw new ToolInputError('Campo "query" deve ser string');
    }
    const normalized = query.trim();
    if (!normalized) {
      throw new ToolInputError('Campo "query" é obrigatório e não pode ser vazio');
    }
    if (normalized.length > MAX_QUERY_CHARS) {
      throw new ToolInputError(`Campo "query" deve ter no máximo ${MAX_QUERY_CHARS} caracteres`);
    }
    return normalized;
  }

  private clampTopK(topK: unknown): number {
    if (topK === undefined || topK === null) {
      return DEFAULT_TOP_K;
    }

    if (typeof topK !== 'number' || Number.isNaN(topK)) {
      throw new ToolInputError('Campo "topK" deve ser number');
    }

    return Math.min(MAX_TOP_K, Math.max(MIN_TOP_K, Math.trunc(topK)));
  }

  private validatePathPrefix(pathPrefix: unknown): string {
    if (pathPrefix === undefined || pathPrefix === null) {
      return '';
    }
    if (typeof pathPrefix !== 'string') {
      throw new ToolInputError('Campo "pathPrefix" deve ser string');
    }
    const normalized = pathPrefix.trim();
    if (normalized.length > MAX_PATH_PREFIX_CHARS) {
      throw new ToolInputError(
        `Campo "pathPrefix" deve ter no máximo ${MAX_PATH_PREFIX_CHARS} caracteres`,
      );
    }
    if (normalized.includes('\0') || normalized.includes('..')) {
      throw new ToolInputError('Campo "pathPrefix" contém sequência inválida');
    }
    return normalized;
  }

  private validateVector(vector: unknown): number[] {
    if (!Array.isArray(vector)) {
      throw new ToolInputError(
        'Campo "vector" é obrigatório neste ambiente. Configure embeddings no Node ou envie o vetor da query.',
      );
    }
    if (vector.length === 0) {
      throw new ToolInputError('Campo "vector" não pode ser vazio');
    }
    if (!vector.every((item) => typeof item === 'number' && Number.isFinite(item))) {
      throw new ToolInputError('Campo "vector" deve conter apenas numbers finitos');
    }
    return vector;
  }

  private mapHitToResult(hit: QdrantSearchHit) {
    const payload = this.ensurePayload(hit.payload);
    const snippet = this.extractSnippet(payload);

    return {
      score: this.ensureScore(hit.score),
      path: this.ensurePath(payload.path),
      startLine: this.toNumberOrNull(payload.startLine ?? payload.start_line),
      endLine: this.toNumberOrNull(payload.endLine ?? payload.end_line),
      snippet,
    };
  }

  private ensurePayload(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object') {
      return {};
    }
    return payload as Record<string, unknown>;
  }

  private ensureScore(score: unknown): number {
    if (typeof score !== 'number' || Number.isNaN(score)) {
      return 0;
    }
    return score;
  }

  private ensurePath(path: unknown): string {
    if (typeof path !== 'string' || !path.trim()) {
      return '(unknown path)';
    }
    const normalized = path.trim();
    return normalized.length > MAX_PATH_PREFIX_CHARS
      ? normalized.slice(0, MAX_PATH_PREFIX_CHARS)
      : normalized;
  }

  private toNumberOrNull(value: unknown): number | null {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return Math.trunc(value);
    }
    return null;
  }

  private extractSnippet(payload: Record<string, unknown>): string {
    const candidate = payload.text;
    if (typeof candidate !== 'string') {
      return '(no snippet)';
    }
    const normalized = candidate.replace(/\s+/g, ' ').trim();
    if (!normalized) {
      return '(no snippet)';
    }

    if (normalized.length <= MAX_SNIPPET_CHARS) {
      return normalized;
    }

    const targetLength = Math.max(MIN_SNIPPET_CHARS, MAX_SNIPPET_CHARS - 3);
    return `${normalized.slice(0, targetLength).trimEnd()}...`;
  }
}
